# Parallel Processing Guide

Run training and prediction workloads across multiple CPU cores by combining KATO's multi-worker server with session-based client parallelism.

## Why parallelism matters

KATO's core compute is Python. By default, a single Python process is limited to one CPU core at a time (the Global Interpreter Lock). Running KATO with multiple **worker processes** lets the server use multiple cores simultaneously, which translates to:

- **Training**: Higher throughput when you have many independent units of data to learn (articles, sessions, examples).
- **Prediction / serving**: More concurrent users, or more concurrent hypotheses for a single user, without queueing.
- **Batch workloads**: Score large batches in less wall-clock time.

KATO supports this via two complementary layers:

1. **Server-side**: `KATO_WORKERS=N` spawns N uvicorn worker processes in the KATO container.
2. **Client-side**: Your application issues concurrent requests, each tied to a separate **session**.

Both pieces matter. Raising only one does not help.

## The two knobs

### KATO_WORKERS (server-side)

Sets how many uvicorn worker processes the KATO container runs. Each worker is an independent Python process with its own interpreter, so they run truly in parallel across cores.

**Configure**:
```bash
# Per-start flag (recommended)
./kato-manager.sh start --workers 4

# Or via env var
KATO_WORKERS=4 ./kato-manager.sh start

# Or via .env file
echo "KATO_WORKERS=4" >> .env
./kato-manager.sh start
```

**Check current setting**:
```bash
./kato-manager.sh status
# ✓ KATO API is responding (KATO_WORKERS=4)
```

Default is 4. You can safely go up to ~(physical cores − 2), leaving headroom for ClickHouse, Redis, and Qdrant.

### Client-side concurrency

How many concurrent sessions / HTTP requests your application issues at once. Can be:
- Python `ThreadPoolExecutor`
- `asyncio` with `aiohttp` or `httpx`
- Separate processes (multiprocessing)
- Distributed workers across machines

Each concurrent unit must use its own **session** — don't share a `session_id` across threads.

### Why they don't have to match exactly

Client threads spend most of their time waiting on HTTP responses, not computing. So one server worker can keep several client threads occupied. Slight oversubscription on the client side (e.g., client concurrency = 1.25 × `KATO_WORKERS`) often gives the best throughput because it keeps all server workers busy even when some requests take longer than others.

**Rule of thumb**: Start with `client_concurrency = KATO_WORKERS`. Tune from there based on observed CPU utilization (see [Tuning](#tuning)).

## How sessions enable parallelism

KATO's session model is designed for this pattern. Every session has:
- Its own **short-term memory (STM)** — the sequence of observations being built up
- Its own **emotive state, configuration, and metadata**

But sessions that share the same `node_id` share the **long-term memory (LTM)** — the patterns learned from past training. So:

- Two sessions training different documents against `node_id="my_model"` **do not interfere** with each other's STM.
- All patterns they learn land in the same shared LTM, available to every future session on that node.
- During prediction, each user gets isolated observation history but draws on the full LTM.

This is what makes parallel training and multi-user serving safe on the same KATO node without data collisions.

## Parallel training

The training loop for each independent unit of data:

1. Create a session on the shared `node_id`
2. `observe` each event from the training unit (a document, a trajectory, a transaction sequence)
3. Call `/learn` to persist the STM as a new pattern in the shared LTM
4. Close (delete) the session

Fan these out across your concurrency layer.

### Basic example: training on independent documents

```python
import requests
from concurrent.futures import ThreadPoolExecutor

KATO_URL = "http://localhost:8000"
NODE_ID = "my_model"
NUM_WORKERS = 4  # match KATO_WORKERS

def train_one_document(document):
    """Train KATO on a single document. Each call uses an isolated session."""
    # 1. Create a session on the shared node
    r = requests.post(f"{KATO_URL}/sessions", json={"node_id": NODE_ID})
    session_id = r.json()["session_id"]

    try:
        # 2. Observe each event in the document
        for event in document["events"]:
            requests.post(
                f"{KATO_URL}/sessions/{session_id}/observe",
                json={"strings": event, "vectors": [], "emotives": {}}
            )

        # 3. Persist as a pattern in the shared LTM
        requests.post(f"{KATO_URL}/sessions/{session_id}/learn")
    finally:
        # 4. Clean up
        requests.delete(f"{KATO_URL}/sessions/{session_id}")

# Training corpus: a list of independent documents
documents = load_training_corpus()

# Fan out across NUM_WORKERS threads
with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
    list(executor.map(train_one_document, documents))
```

With `KATO_WORKERS=4` and `NUM_WORKERS=4`, this processes ~4 documents simultaneously. On a 12-core machine, `KATO_WORKERS=8` with `NUM_WORKERS=8` can get closer to a 7–8× speedup over single-worker.

### What counts as an "independent unit"?

Anything where order-of-training doesn't matter for correctness:
- ✅ Documents in a corpus
- ✅ User sessions in a log
- ✅ Trajectories of a robot from different runs
- ✅ Time-windowed batches of transactions
- ❌ Tokens within a single document (these must stay in order — train them sequentially inside one session)

Sharing is at the pattern level: KATO's deduplication (via atomic Redis `SETNX` on the pattern hash) ensures two threads learning the same sequence don't double-count it in the LTM.

## Parallel prediction and serving

At inference time, multi-worker KATO gives you three distinct benefits:

### 1. Multi-user serving

Each user gets their own session. Their STM holds their individual interaction history; predictions draw on the shared LTM of all patterns ever learned for that `node_id`. This is the natural setup for chatbots, recommenders, and any multi-tenant service.

```python
def handle_user_observation(user_id, observation):
    session_id = get_or_create_user_session(user_id, node_id="recommender")

    requests.post(
        f"{KATO_URL}/sessions/{session_id}/observe",
        json={"strings": observation}
    )

    return requests.get(
        f"{KATO_URL}/sessions/{session_id}/predictions"
    ).json()
```

With `KATO_WORKERS=8`, you can serve ~8 concurrent user requests at full speed before queueing kicks in.

### 2. Concurrent hypothesis evaluation (for a single user)

Sometimes you want to evaluate **several alternative futures in parallel** for the same agent — "what if I observe X next? vs Y next? vs Z next?" Spin up one session per hypothesis, run them concurrently, compare predictions.

```python
def score_hypothesis(base_history, candidate_continuation):
    r = requests.post(f"{KATO_URL}/sessions", json={"node_id": "agent"})
    session_id = r.json()["session_id"]
    try:
        # Replay base history
        for event in base_history:
            requests.post(f"{KATO_URL}/sessions/{session_id}/observe",
                         json={"strings": event})
        # Apply candidate continuation
        for event in candidate_continuation:
            requests.post(f"{KATO_URL}/sessions/{session_id}/observe",
                         json={"strings": event})
        # Score it
        predictions = requests.get(
            f"{KATO_URL}/sessions/{session_id}/predictions"
        ).json()
        return predictions["predictions"][0]["potential"] if predictions["predictions"] else 0.0
    finally:
        requests.delete(f"{KATO_URL}/sessions/{session_id}")

# Evaluate 8 alternative continuations in parallel
with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
    scores = list(executor.map(
        lambda cand: score_hypothesis(current_history, cand),
        candidate_futures
    ))

best_idx = scores.index(max(scores))
```

### 3. Batch prediction throughput

A queue of independent prediction requests (scoring a batch of records, backtesting on a window of data). Fan out with one session per item.

```python
def score_item(item):
    r = requests.post(f"{KATO_URL}/sessions", json={"node_id": "scorer"})
    session_id = r.json()["session_id"]
    try:
        for event in item["history"]:
            requests.post(f"{KATO_URL}/sessions/{session_id}/observe",
                         json={"strings": event})
        return requests.get(
            f"{KATO_URL}/sessions/{session_id}/predictions"
        ).json()
    finally:
        requests.delete(f"{KATO_URL}/sessions/{session_id}")

with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
    results = list(executor.map(score_item, batch))
```

## Tuning

### Step 1: Match client to server, then measure

```python
NUM_WORKERS = KATO_WORKERS  # start here
```

Run your workload and observe CPU on the KATO container:

```bash
docker stats kato
```

### Step 2: Interpret CPU utilization

| Observed CPU | Meaning | Action |
|---|---|---|
| All workers ~100% | Server is saturated, client is the right size | Raise `KATO_WORKERS` (needs restart) for more speed |
| Workers mixed (some 100%, some idle) | Client concurrency too low | Raise `NUM_WORKERS` |
| All workers well under ~60% | Bottleneck is elsewhere (DB, network) | Check ClickHouse / Redis / Qdrant, not worker counts |

### Step 3: Watch tail latency

Oversubscribing the client (e.g., `NUM_WORKERS = 3 × KATO_WORKERS`) can increase throughput slightly but lengthens the tail of request latencies as requests queue. If your use case cares about p99 latency (e.g., interactive serving), keep oversubscription modest (≤ 1.5×).

### Step 4: Consider the data path bottleneck

For **training at very high concurrency**, ClickHouse's insert path can become the bottleneck before Python workers do. KATO's server-side `async_insert` batches writes across all workers automatically, which smooths this out. If you're seeing slow `/learn` calls, check `docker stats kato-clickhouse` — if it's pegged, adding more KATO workers won't help.

## Worked examples

### Example A: Training a recommendation engine on user sessions

You have a log of user browsing sessions. Each session is a sequence of items a user interacted with. You want KATO to learn typical item sequences, then predict the next item for a new user.

```python
import requests
from concurrent.futures import ThreadPoolExecutor

KATO_URL = "http://localhost:8000"
NODE_ID = "recommender"
NUM_WORKERS = 6  # running KATO_WORKERS=6

def train_user_session(user_session):
    r = requests.post(f"{KATO_URL}/sessions", json={"node_id": NODE_ID})
    sid = r.json()["session_id"]
    try:
        for interaction in user_session:
            requests.post(
                f"{KATO_URL}/sessions/{sid}/observe",
                json={
                    "strings": [interaction["item_id"]],
                    "emotives": {"engagement": interaction["dwell_time_score"]}
                }
            )
        requests.post(f"{KATO_URL}/sessions/{sid}/learn")
    finally:
        requests.delete(f"{KATO_URL}/sessions/{sid}")

# Millions of historical user sessions → fan out across threads
user_sessions = load_historical_sessions()

with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
    list(pool.map(train_user_session, user_sessions))
```

**Then, at serving time**, the same KATO instance handles live predictions for real users concurrently — each user's live session is isolated, but they all draw on the patterns just learned:

```python
# FastAPI service serving live recommendations
@app.post("/recommend")
def recommend(user_id: str, item_id: str):
    sid = live_session_store.get_or_create(user_id, node_id=NODE_ID)
    requests.post(f"{KATO_URL}/sessions/{sid}/observe",
                  json={"strings": [item_id]})
    preds = requests.get(f"{KATO_URL}/sessions/{sid}/predictions").json()
    return {"next_items": [p["future"] for p in preds["predictions"][:10]]}
```

### Example B: Hierarchical training (multi-layer abstractions)

When training a model of patterns-of-patterns — layer 0 learns token sequences, layer 1 learns sequences of layer-0 pattern names, layer 2 learns sequences of layer-1 pattern names, etc. Each layer is a separate `node_id`. One document flows through all layers.

```python
LAYERS = ["layer0", "layer1", "layer2", "layer3"]
NUM_WORKERS = 5  # running KATO_WORKERS=5

def train_document_all_layers(document):
    """Feed the document through each layer. Output pattern name of layer N
    becomes the only token observed at layer N+1 — so layer N+1 learns
    sequences of layer N's patterns."""
    sessions = {}
    try:
        for layer in LAYERS:
            r = requests.post(f"{KATO_URL}/sessions", json={"node_id": layer})
            sessions[layer] = r.json()["session_id"]

        current_events = document["events"]
        for layer in LAYERS:
            sid = sessions[layer]
            for event in current_events:
                requests.post(f"{KATO_URL}/sessions/{sid}/observe",
                              json={"strings": event})
            learn_result = requests.post(
                f"{KATO_URL}/sessions/{sid}/learn"
            ).json()
            pattern_name = learn_result["pattern_name"]
            # Next layer observes this single pattern name
            current_events = [[pattern_name]]
    finally:
        for sid in sessions.values():
            requests.delete(f"{KATO_URL}/sessions/{sid}")

documents = load_corpus()
with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
    list(pool.map(train_document_all_layers, documents))
```

Each worker thread threads one document through all 4 layers end-to-end. With 5 threads and 5 KATO workers, up to 5 documents are in flight across the hierarchy at once.

### Example C: Batch-scoring a portfolio of time series

You have 10,000 stocks and want KATO's prediction output for each based on its recent price history. Each stock's history is independent.

```python
NUM_WORKERS = 8

def score_stock(ticker_history):
    r = requests.post(f"{KATO_URL}/sessions", json={"node_id": "markets"})
    sid = r.json()["session_id"]
    try:
        for bar in ticker_history["recent_bars"]:
            requests.post(f"{KATO_URL}/sessions/{sid}/observe",
                          json={"strings": bar["discretized_signals"]})
        preds = requests.get(
            f"{KATO_URL}/sessions/{sid}/predictions"
        ).json()
        return {
            "ticker": ticker_history["ticker"],
            "top_prediction": preds["predictions"][0] if preds["predictions"] else None
        }
    finally:
        requests.delete(f"{KATO_URL}/sessions/{sid}")

with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
    scores = list(pool.map(score_stock, portfolio))
```

## Picking a starting configuration

| Workload shape | `KATO_WORKERS` | Client concurrency |
|---|---|---|
| Single-user interactive (chatbot dev) | 1–2 | 1 |
| Multi-user serving, light load | 4 | up to ~10 (mostly idle threads) |
| Multi-user serving, heavy load | (cores − 2) | 1–1.5× KATO_WORKERS |
| Batch training, modest dataset | 4 | 4–5 |
| Batch training, large dataset on dedicated host | (cores − 2) | = KATO_WORKERS |

## Gotchas

- **One session per concurrent unit.** Never reuse the same `session_id` across threads. STM is not thread-safe per session. If two threads need to share observation history, they're not independent work and shouldn't be parallelized this way.
- **Raising `KATO_WORKERS` requires a container restart** (`./kato-manager.sh restart kato --workers N`). Raising client concurrency is free.
- **Same `node_id` means shared patterns.** Two parallel training runs against the same `node_id` will both contribute to the same LTM. If you want independent models, use different `node_id`s.
- **Very high client concurrency** (e.g., 50 threads against 4 workers) won't crash KATO, but throughput plateaus and tail latency grows. Prefer adding server workers over piling up client threads.
- **Don't set `KATO_WORKERS` higher than physical cores.** You'll just thrash the scheduler. Leave headroom for ClickHouse and Redis.
- **Finalization blocks briefly.** The `/learn` call that persists a pattern returns quickly, but periodic finalization inside KATO (e.g., recomputing global metrics) performs a ClickHouse flush that can take ~200 ms. Not an issue for throughput, but something to know if you see occasional slightly slower `/learn` calls.

## See also

- [Session Management Guide](session-management.md) — lifecycle, TTL, configuration
- [Pattern Learning Guide](pattern-learning.md) — what gets learned, auto-learn triggers
- [Python Client Library](python-client.md) — a more complete client than the snippets here
- [Operations: Scaling](../operations/scaling.md) — infrastructure-side scaling, load balancers, multi-instance

---

**Last Updated**: April 2026
**KATO Version**: 3.10.0+
