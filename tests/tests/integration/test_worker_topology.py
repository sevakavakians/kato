"""
Worker-topology tests for cross-process behaviour.

KATO runs under multi-worker uvicorn (KATO_WORKERS, default 4). Anything that
lives inside one Python process — the WebSocket EventBroadcaster's connection
list, the per-process /sessions/count cache — only behaves correctly if it is
either shared across workers or converges within its documented window. These
tests launch a dedicated kato:latest container per worker count and assert the
same contract against each, so a cross-worker failure is reproduced on every
run instead of being left to the kernel's accept() scheduling.

Determinism:
- The container's worker count is verified from uvicorn's per-worker
  "Started server process [pid]" startup lines, not inferred from traffic.
- Every WebSocket state.snapshot and /health response carries `worker_pid`.
  A test proves it holds connections on at least two distinct workers before
  asserting that an event reaches all of them; given that, an in-process
  broadcaster fails on every run, never by chance.
- /sessions/count is read only after its cache TTL has elapsed, so every
  worker must have recomputed from the shared Redis index.

Requires the docker CLI, the kato:latest image, and the compose `kato`
container (its environment and network are copied so the test containers are
configured identically apart from the variables under test).
"""

import asyncio
import contextlib
import json
import logging
import os
import re
import socket
import subprocess
import time
import uuid

import pytest
import requests
import websockets

logger = logging.getLogger(__name__)

WORKER_COUNTS = (1, 2, 4)
IMAGE = os.environ.get("KATO_TOPOLOGY_IMAGE", "kato:latest")
REFERENCE_CONTAINER = os.environ.get("KATO_TOPOLOGY_REFERENCE_CONTAINER", "kato")
# Short cache TTL keeps the count tests fast; the contract (converges within
# the TTL on every worker) is the same for any value.
SESSION_COUNT_CACHE_TTL = 2.0
STARTUP_TIMEOUT = 120.0
EVENT_TIMEOUT = 5.0

# Environment copied from the reference container, minus image/runtime vars.
_ENV_BLOCKLIST = {"PATH", "LANG", "HOME", "HOSTNAME", "GPG_KEY", "PYTHON_VERSION",
                  "PYTHON_SHA256", "PYTHONUNBUFFERED"}

_STARTED_WORKER_RE = re.compile(r"Started server process \[(\d+)\]")
_STARTUP_COMPLETE = "Application startup complete."


def _docker(*args, check=True, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          check=check, timeout=timeout)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class KatoTopology:
    """A throwaway KATO container running a specific number of uvicorn workers."""

    def __init__(self, workers: int):
        self.workers = workers
        self.name = f"kato-topology-w{workers}-{uuid.uuid4().hex[:8]}"
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.ws_url = f"ws://127.0.0.1:{self.port}/ws/events"
        self.session_count_cache_ttl = SESSION_COUNT_CACHE_TTL
        self.worker_pids: set[int] = set()

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        env, network = self._reference_config()
        env["KATO_WORKERS"] = str(self.workers)
        env["SESSION_COUNT_CACHE_TTL_SECONDS"] = str(self.session_count_cache_ttl)

        cmd = ["run", "-d", "--rm", "--name", self.name, "--network", network,
               "-p", f"127.0.0.1:{self.port}:8000"]
        for key, value in sorted(env.items()):
            cmd += ["-e", f"{key}={value}"]
        cmd.append(IMAGE)
        _docker(*cmd)
        try:
            self._wait_until_all_workers_ready()
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        _docker("rm", "-f", self.name, check=False)

    def logs(self) -> str:
        result = _docker("logs", self.name, check=False)
        return result.stdout + result.stderr

    # -- helpers -------------------------------------------------------------

    def _reference_config(self) -> tuple[dict[str, str], str]:
        result = _docker("inspect", REFERENCE_CONTAINER, "--format",
                         '{{json .Config.Env}}\n{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}',
                         check=False)
        if result.returncode != 0:
            pytest.skip(f"reference container '{REFERENCE_CONTAINER}' not running; "
                        "cannot copy its config for topology containers")
        env_json, network = result.stdout.strip().split("\n", 1)
        env = {}
        for item in json.loads(env_json):
            key, _, value = item.partition("=")
            if key not in _ENV_BLOCKLIST:
                env[key] = value
        return env, network.strip()

    def _wait_until_all_workers_ready(self) -> None:
        """Ready means every worker logged startup complete and /health answers."""
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            logs = self.logs()
            started = {int(pid) for pid in _STARTED_WORKER_RE.findall(logs)}
            if (len(started) == self.workers
                    and logs.count(_STARTUP_COMPLETE) >= self.workers):
                try:
                    if requests.get(f"{self.base_url}/health", timeout=2).status_code == 200:
                        self.worker_pids = started
                        return
                except requests.RequestException:
                    pass
            time.sleep(0.5)
        raise RuntimeError(
            f"{self.name} did not bring up {self.workers} workers within "
            f"{STARTUP_TIMEOUT}s. Logs:\n{self.logs()[-3000:]}")

    # -- traffic helpers -----------------------------------------------------

    def create_session(self, node_id: str) -> str:
        resp = requests.post(f"{self.base_url}/sessions", json={
            "node_id": node_id, "config": {}, "metadata": {}, "ttl_seconds": 60})
        assert resp.status_code == 200, resp.text
        return resp.json()["session_id"]

    def delete_session(self, session_id: str) -> None:
        resp = requests.delete(f"{self.base_url}/sessions/{session_id}")
        assert resp.status_code in (200, 404), resp.text

    def read_count_from_each_worker(self) -> list[int]:
        """Read /sessions/count over fresh connections, enough to reach every worker."""
        counts = []
        for _ in range(8 * self.workers):
            resp = requests.get(f"{self.base_url}/sessions/count", timeout=5,
                                headers={"Connection": "close"})
            resp.raise_for_status()
            counts.append(resp.json()["active_session_count"])
        return counts

    def health_pids(self, samples: int) -> set[int]:
        pids = set()
        for _ in range(samples):
            resp = requests.get(f"{self.base_url}/health", timeout=5,
                                headers={"Connection": "close"})
            resp.raise_for_status()
            pids.add(resp.json()["worker_pid"])
        return pids


@pytest.fixture(scope="module", params=WORKER_COUNTS, ids=[f"workers={n}" for n in WORKER_COUNTS])
def topology(request) -> KatoTopology:
    topo = KatoTopology(request.param)
    topo.start()
    logger.info("Started %s on %s with worker pids %s", topo.name, topo.base_url, sorted(topo.worker_pids))
    yield topo
    topo.stop()


class WsClient:
    """One WebSocket client plus the worker pid that owns it."""

    def __init__(self, ws, pid: int):
        self.ws = ws
        self.pid = pid

    async def next_event(self):
        return json.loads(await asyncio.wait_for(self.ws.recv(), timeout=EVENT_TIMEOUT))


async def _connect_clients_spanning_workers(topology: KatoTopology) -> list[WsClient]:
    """Open WebSocket clients until they provably sit on >=2 distinct workers.

    For a single-worker topology this opens three clients and checks they all
    report the one known pid. For multi-worker topologies it keeps connecting
    (bounded) until at least two distinct worker pids hold a client, so any
    later "every client receives the event" assertion can only pass if
    delivery crosses process boundaries.
    """
    clients: list[WsClient] = []
    minimum_clients = 3
    max_attempts = 16 * topology.workers
    try:
        while len(clients) < max_attempts:
            ws = await websockets.connect(topology.ws_url)
            snapshot = json.loads(await asyncio.wait_for(ws.recv(), timeout=EVENT_TIMEOUT))
            assert snapshot["event_type"] == "state.snapshot"
            pid = snapshot["data"]["worker_pid"]
            assert pid in topology.worker_pids, \
                f"snapshot came from pid {pid}, not one of the started workers {sorted(topology.worker_pids)}"
            clients.append(WsClient(ws, pid))

            distinct = {c.pid for c in clients}
            if len(clients) >= minimum_clients and (topology.workers == 1 or len(distinct) >= 2):
                return clients
        pytest.fail(
            f"Could not place WebSocket clients on two distinct workers after {max_attempts} "
            f"connections; all landed on {sorted({c.pid for c in clients})} "
            f"of {sorted(topology.worker_pids)}")
    except BaseException:
        await _close_all(clients)
        raise


async def _close_all(clients: list[WsClient]) -> None:
    for client in clients:
        with contextlib.suppress(Exception):
            await client.ws.close()


async def _collect(clients: list[WsClient], event_type: str, session_id: str) -> tuple[list[dict], list[int]]:
    """Return (events received, pids of clients that saw nothing)."""
    received, missed = [], []
    for client in clients:
        try:
            event = await client.next_event()
        except asyncio.TimeoutError:
            missed.append(client.pid)
            continue
        assert event["event_type"] == event_type, event
        assert event["data"]["session_id"] == session_id, event
        received.append(event)
    return received, missed


# ---------------------------------------------------------------------------
# Topology sanity
# ---------------------------------------------------------------------------

def test_container_runs_requested_worker_count(topology: KatoTopology):
    """The container really has N uvicorn workers, and /health is served by them."""
    assert len(topology.worker_pids) == topology.workers

    observed = topology.health_pids(samples=32 * topology.workers)
    assert observed <= topology.worker_pids, \
        f"/health answered from unknown pids {sorted(observed - topology.worker_pids)}"
    if topology.workers == 1:
        assert observed == topology.worker_pids
    else:
        assert len(observed) >= 2, \
            f"connections never spread beyond one worker: {sorted(observed)} of {sorted(topology.worker_pids)}"


# ---------------------------------------------------------------------------
# WebSocket event delivery
# ---------------------------------------------------------------------------

async def test_session_created_event_reaches_every_client(topology: KatoTopology):
    """session.created must reach every connected client, whichever worker created it."""
    clients = await _connect_clients_spanning_workers(topology)
    session_id = None
    try:
        session_id = topology.create_session("topology_created")
        received, missed = await _collect(clients, "session.created", session_id)

        assert not missed, (
            f"session.created for {session_id} never reached clients on worker pids "
            f"{sorted(set(missed))}; it reached {len(received)} client(s) on "
            f"{sorted({c.pid for c in clients if c.pid not in missed})}. "
            f"Events are only delivered inside the worker that served the HTTP request.")
        for event in received:
            assert event["data"]["node_id"] == "topology_created"
            assert "created_at" in event["data"]
            assert "timestamp" in event
    finally:
        if session_id:
            topology.delete_session(session_id)
        await _close_all(clients)


async def test_session_destroyed_event_reaches_every_client(topology: KatoTopology):
    """session.destroyed must reach every connected client, whichever worker deleted it."""
    session_id = topology.create_session("topology_destroyed")
    clients = await _connect_clients_spanning_workers(topology)
    try:
        topology.delete_session(session_id)
        received, missed = await _collect(clients, "session.destroyed", session_id)

        assert not missed, (
            f"session.destroyed for {session_id} never reached clients on worker pids "
            f"{sorted(set(missed))}; it reached {len(received)} client(s) on "
            f"{sorted({c.pid for c in clients if c.pid not in missed})}. "
            f"Events are only delivered inside the worker that served the HTTP request.")
        for event in received:
            assert event["data"]["reason"] == "explicit_delete"
            assert "destroyed_at" in event["data"]
    finally:
        await _close_all(clients)


async def test_client_sees_full_session_lifecycle_in_order(topology: KatoTopology):
    """Each client sees session.created then session.destroyed, in that order.

    This is the Quick Start Guide flow (connect → create → delete), asserted for
    a client on every worker rather than a single client whose worker happens
    to match the one serving the HTTP requests.
    """
    clients = await _connect_clients_spanning_workers(topology)
    try:
        session_id = topology.create_session("topology_lifecycle")
        _, missed_created = await _collect(clients, "session.created", session_id)
        topology.delete_session(session_id)
        # Only clients that saw the creation can be expected to see the deletion
        # in order; clients that missed it are reported by the assertion below.
        survivors = [c for c in clients if c.pid not in missed_created]
        _, missed_destroyed = await _collect(survivors, "session.destroyed", session_id)

        assert not missed_created and not missed_destroyed, (
            f"lifecycle events for {session_id} did not reach every client: "
            f"missed created on pids {sorted(set(missed_created))}, "
            f"missed destroyed on pids {sorted(set(missed_destroyed))}")
    finally:
        await _close_all(clients)


# ---------------------------------------------------------------------------
# /sessions/count across workers
# ---------------------------------------------------------------------------

def test_session_count_converges_on_every_worker(topology: KatoTopology):
    """After the count cache TTL, every worker reports the true active-session count."""
    settle = topology.session_count_cache_ttl + 0.5

    def settled_count() -> int:
        time.sleep(settle)
        counts = topology.read_count_from_each_worker()
        assert len(set(counts)) == 1, \
            f"workers disagree on active session count after cache TTL: {sorted(set(counts))}"
        return counts[0]

    baseline = settled_count()

    created = [topology.create_session(f"topology_count_{i}") for i in range(5)]
    after_create = settled_count()
    assert after_create == baseline + 5, \
        f"expected {baseline + 5} active sessions after creating 5, got {after_create}"

    for session_id in created:
        topology.delete_session(session_id)
    after_delete = settled_count()
    assert after_delete == baseline, \
        f"expected count to return to {baseline} after deleting 5, got {after_delete}"
