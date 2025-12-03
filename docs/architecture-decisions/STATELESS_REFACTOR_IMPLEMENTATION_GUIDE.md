# KATO Stateless Processor Refactor - Detailed Implementation Plan

**Status**: Phase 1.1 ✅ Complete | Phase 1.2-1.10 📋 This Document

This document provides file-by-file, line-by-line guidance for completing the stateless processor refactor.

---

## TABLE OF CONTENTS

1. [Overview](#overview)
2. [Phase 1.2: Update KatoProcessor.__init__()](#phase-12-update-katoprocessor__init__)
3. [Phase 1.3: Update observe() Method](#phase-13-update-observe-method)
4. [Phase 1.4: Update get_predictions() Method](#phase-14-update-get_predictions-method)
5. [Phase 1.5: Update learn() Method](#phase-15-update-learn-method)
6. [Phase 1.6: Update observation_processor.py](#phase-16-update-observation_processorpy)
7. [Phase 1.7: Update pattern_operations.py](#phase-17-update-pattern_operationspy)
8. [Phase 1.8: Update Session Endpoints](#phase-18-update-session-endpoints)
9. [Phase 1.9-1.10: Remove Processor Locks](#phase-19-110-remove-processor-locks)

---

## OVERVIEW

### What We're Doing

Converting `KatoProcessor` from **stateful** (holding session data as instance variables) to **stateless** (accepting session data as parameters).

### Key Principle

```python
# BEFORE (Stateful):
processor.time = 5          # Mutation - BAD
result = processor.observe(obs)

# AFTER (Stateless):
new_state = processor.observe(obs, session_state=session)  # Pure function - GOOD
```

### Files to Modify

1. `kato/workers/kato_processor.py` ⭐ **CRITICAL**
2. `kato/workers/observation_processor.py`
3. `kato/workers/pattern_operations.py`
4. `kato/api/endpoints/sessions.py` (7 endpoints)
5. `kato/processors/processor_manager.py` (remove locks)

---

## PHASE 1.2: Update KatoProcessor.__init__()

**File**: `kato/workers/kato_processor.py`

### Current Code (Lines 20-97)

```python
class KatoProcessor:
    def __init__(self, name: str, processor_id: str, settings=None, **genome_manifest):
        # ... settings and logging setup ...

        self.id = processor_id
        self.name = name
        self.time = 0  # ❌ REMOVE - session-specific

        # ... processor setup ...

        self.memory_manager = MemoryManager(self.pattern_processor, self.vector_processor)

        # ... module initialization ...

        # Initialize state through memory manager
        self.memory_manager.reset_primitive_variables()  # ❌ BROKEN - MemoryManager is stateless now

        # Expose commonly accessed attributes for backward compatibility
        self.symbols = self.memory_manager.symbols  # ❌ REMOVE - doesn't exist anymore
        self.current_emotives = self.memory_manager.current_emotives  # ❌ REMOVE
        self.percept_data = self.memory_manager.percept_data  # ❌ REMOVE
        self.time = self.memory_manager.time  # ❌ REMOVE

        self.predictions = []  # ❌ REMOVE - session-specific
```

### New Code

```python
class KatoProcessor:
    def __init__(self, name: str, processor_id: str, settings=None, **genome_manifest):
        # ... settings and logging setup (KEEP AS-IS) ...

        self.id = processor_id
        self.name = name
        # REMOVE: self.time = 0

        # ... processor setup (KEEP AS-IS) ...

        # MemoryManager is now stateless helper (still instantiate for method access)
        self.memory_manager = MemoryManager(self.pattern_processor, self.vector_processor)

        # ... module initialization (KEEP AS-IS) ...

        # REMOVE: self.memory_manager.reset_primitive_variables()
        # REMOVE: self.symbols = self.memory_manager.symbols
        # REMOVE: self.current_emotives = self.memory_manager.current_emotives
        # REMOVE: self.percept_data = self.memory_manager.percept_data
        # REMOVE: self.time = self.memory_manager.time
        # REMOVE: self.predictions = []

        logger.info(f"KatoProcessor initialized (stateless): {self.id}")
```

### Summary of Changes

**REMOVE** (Lines to delete):
- Line 42: `self.time = 0`
- Line 91: `self.memory_manager.reset_primitive_variables()`
- Lines 94-97: All attribute exposures (`self.symbols`, `self.current_emotives`, etc.)
- Line 99: `self.predictions = []`

**KEEP** (No changes):
- All LTM processor setup (pattern_processor, vector_processor)
- MemoryManager instantiation (still needed for method access)
- Settings and logging setup

---

## PHASE 1.3: Update observe() Method

**File**: `kato/workers/kato_processor.py`

### Current Signature (Line ~200)

```python
async def observe(self, observation: dict, config: SessionConfiguration = None) -> dict:
    """
    Process an observation and update memory state.
    """
    # Uses self.time, self.symbols, self.percept_data, etc. (MUTATION)
```

### New Signature

```python
async def observe(
    self,
    observation: dict,
    *,
    session_state: 'SessionState',
    config: SessionConfiguration
) -> dict:
    """
    Process an observation and return updated session state.

    STATELESS: Takes session state as input, returns new state as output.
    Does NOT mutate processor instance or session_state input.

    Args:
        observation: Observation data (strings, vectors, emotives, metadata)
        session_state: Current session state (SessionState from Redis)
        config: Session configuration

    Returns:
        Dictionary with updated state:
        {
            'status': 'okay',
            'stm': list[list[str]],              # New STM
            'time': int,                         # New time
            'emotives_accumulator': list[dict],  # New emotives
            'metadata_accumulator': list[dict],  # New metadata
            'percept_data': dict,                # New percept
            'predictions': list,                 # New predictions
            'auto_learned_pattern': str | None,  # If auto-learn triggered
            'unique_id': str
        }
    """
```

### Implementation Changes

**CURRENT CODE PATTERN** (what to find):
```python
async def observe(self, observation: dict, config: SessionConfiguration = None) -> dict:
    # 1. Access instance variables
    current_stm = self.memory_manager.get_stm_state()
    self.time += 1
    self.symbols.append(...)

    # 2. Process observation
    result = self.observation_processor.process(observation, config)

    # 3. Mutate instance state
    self.percept_data = result['percept_data']
    self.predictions = result['predictions']

    return {'status': 'okay'}
```

**NEW CODE PATTERN** (what to replace with):
```python
async def observe(
    self,
    observation: dict,
    *,
    session_state: 'SessionState',
    config: SessionConfiguration
) -> dict:
    # 1. Load session STM into pattern processor (temporary, for processing)
    self.memory_manager.set_stm_in_pattern_processor(
        self.pattern_processor,
        session_state.stm
    )

    # 2. Process observation using session state (no mutation)
    result = await self.observation_processor.process(
        observation,
        session_state=session_state,
        config=config
    )

    # 3. Build new state (no mutation of inputs)
    new_stm = self.memory_manager.get_stm_from_pattern_processor(self.pattern_processor)
    new_time = MemoryManager.increment_time(session_state.time)

    # Process emotives
    new_emotives_acc, new_current_emotives = MemoryManager.process_emotives(
        session_state.emotives_accumulator,
        observation.get('emotives', {})
    )

    # Process metadata
    new_metadata_acc = MemoryManager.process_metadata(
        session_state.metadata_accumulator,
        observation.get('metadata', {})
    )

    # Build percept data
    new_percept = MemoryManager.build_percept_data(
        strings=result.get('strings', []),
        vectors=result.get('vectors', []),
        emotives=new_current_emotives,
        path=result.get('path', []),
        metadata=observation.get('metadata', {})
    )

    # 4. Return new state (no mutation)
    return {
        'status': 'okay',
        'stm': new_stm,
        'time': new_time,
        'emotives_accumulator': new_emotives_acc,
        'metadata_accumulator': new_metadata_acc,
        'percept_data': new_percept,
        'predictions': result.get('predictions', []),
        'auto_learned_pattern': result.get('auto_learned_pattern'),
        'unique_id': observation.get('unique_id', '')
    }
```

### Detailed Steps

1. **Change method signature** - Add `session_state` and make `config` required (no default)
2. **Remove all `self.` state access** - Replace with `session_state.`
3. **Remove all `self.` state mutation** - Build new values instead
4. **Use MemoryManager static methods** - All state transformations go through stateless helpers
5. **Return new state dict** - Caller updates SessionState in Redis

---

## PHASE 1.4: Update get_predictions() Method

**File**: `kato/workers/kato_processor.py`

### Current Signature

```python
async def get_predictions(self, config: SessionConfiguration = None) -> list:
    """Get predictions based on current STM"""
    # Uses self.pattern_processor.STM, self.predictions
```

### New Signature

```python
async def get_predictions(
    self,
    *,
    session_state: 'SessionState',
    config: SessionConfiguration
) -> list:
    """
    Get predictions based on session STM.

    STATELESS: Takes session state, returns predictions.
    Does NOT mutate processor or session_state.

    Args:
        session_state: Current session state
        config: Session configuration

    Returns:
        List of prediction objects
    """
```

### Implementation Changes

```python
async def get_predictions(
    self,
    *,
    session_state: 'SessionState',
    config: SessionConfiguration
) -> list:
    # Load session STM into pattern processor (temporary)
    self.memory_manager.set_stm_in_pattern_processor(
        self.pattern_processor,
        session_state.stm
    )

    # Get predictions using config
    predictions = await self.pattern_processor.get_predictions(
        recall_threshold=config.recall_threshold,
        max_predictions=config.max_predictions,
        use_token_matching=config.use_token_matching,
        rank_sort_algo=config.rank_sort_algo
    )

    return predictions
```

---

## PHASE 1.5: Update learn() Method

**File**: `kato/workers/kato_processor.py`

### Current Signature

```python
def learn(self) -> str:
    """Learn a pattern from current STM"""
    # Uses self.pattern_processor.STM, self.memory_manager
```

### New Signature

```python
def learn(
    self,
    *,
    session_state: 'SessionState'
) -> dict:
    """
    Learn a pattern from session STM.

    STATELESS: Takes session state, returns pattern name and updated STM.
    Does NOT mutate processor or session_state.

    Args:
        session_state: Current session state

    Returns:
        Dictionary:
        {
            'pattern_name': str,
            'stm': list[list[str]]  # Updated STM after learning
        }
    """
```

### Implementation Changes

```python
def learn(
    self,
    *,
    session_state: 'SessionState'
) -> dict:
    # Load session STM into pattern processor
    self.memory_manager.set_stm_in_pattern_processor(
        self.pattern_processor,
        session_state.stm
    )

    # Learn pattern (writes to LTM - side effect OK, that's shared)
    pattern_name = self.pattern_processor.learn()

    # Get updated STM (pattern processor may have modified it)
    new_stm = self.memory_manager.get_stm_from_pattern_processor(self.pattern_processor)

    return {
        'pattern_name': pattern_name,
        'stm': new_stm
    }
```

---

## PHASE 1.6: Update observation_processor.py

**File**: `kato/workers/observation_processor.py`

### Current Structure

```python
class ObservationProcessor:
    def __init__(self, vector_processor, pattern_processor, memory_manager, ...):
        self.memory_manager = memory_manager  # Has instance state

    async def process(self, observation, config):
        # Accesses self.memory_manager.symbols, .time, etc.
        self.memory_manager.symbols.append(...)  # MUTATION
```

### Changes Needed

1. **Update `process()` signature**:
```python
async def process(
    self,
    observation: dict,
    *,
    session_state: 'SessionState',
    config: SessionConfiguration
) -> dict:
    """
    Process observation using session state.

    Args:
        observation: Observation data
        session_state: Current session state
        config: Session configuration

    Returns:
        Dictionary with processing results
    """
```

2. **Replace all state access**:
```python
# BEFORE:
self.memory_manager.symbols.append(symbol)  # MUTATION

# AFTER:
new_symbols = MemoryManager.add_symbols(session_state.symbols, [symbol])
# Return new_symbols in result dict
```

3. **Return new state in result**:
```python
return {
    'symbols': new_symbols,
    'strings': processed_strings,
    'vectors': processed_vectors,
    'predictions': predictions,
    # ... other results
}
```

### Specific Methods to Update

- `process()` - Main processing method
- Any helper methods that access memory_manager state

---

## PHASE 1.7: Update pattern_operations.py

**File**: `kato/workers/pattern_operations.py`

### Current Structure

```python
class PatternOperations:
    def __init__(self, pattern_processor, vector_processor, memory_manager):
        self.memory_manager = memory_manager

    def some_operation(self):
        # Accesses self.memory_manager.emotives, .metadata, etc.
```

### Changes Needed

**If methods access memory_manager state:**

1. Add `session_state` parameter to method signatures
2. Replace `self.memory_manager.x` with `session_state.x`
3. Return new state values instead of mutating

**Pattern**:
```python
# BEFORE:
def operation(self):
    self.memory_manager.emotives.append(new_emotive)

# AFTER:
def operation(self, session_state: 'SessionState'):
    new_emotives = MemoryManager.process_emotives(
        session_state.emotives_accumulator,
        new_emotive
    )
    return new_emotives
```

---

## PHASE 1.8: Update Session Endpoints

**File**: `kato/api/endpoints/sessions.py`

All 7 endpoints need the same pattern change. Here's the template:

### Pattern: BEFORE (Stateful with Locks)

```python
@router.post("/{session_id}/observe")
async def observe_in_session(session_id: str, data: ObservationData):
    session = await session_manager.get_session(session_id)
    processor = await processor_manager.get_processor(session.node_id)

    lock = await session_manager.get_session_lock(session_id)
    async with lock:
        # LOCK 1: Session lock
        processor_lock = processor_manager.get_processor_lock(session.node_id)
        async with processor_lock:
            # LOCK 2: Processor lock ❌ REMOVE THIS

            # Load state into processor (MUTATION)
            processor.set_stm(session.stm)
            processor.set_emotives_accumulator(session.emotives)
            processor.time = session.time

            # Process (mutates processor)
            result = await processor.observe(observation, config=session.config)

            # Read mutated state back
            session.stm = processor.get_stm()
            session.emotives = processor.get_emotives_accumulator()
            session.time = processor.time

        await session_manager.update_session(session)

    return result
```

### Pattern: AFTER (Stateless, No Processor Lock)

```python
@router.post("/{session_id}/observe")
async def observe_in_session(session_id: str, data: ObservationData):
    session = await session_manager.get_session(session_id)
    processor = await processor_manager.get_processor(session.node_id)

    lock = await session_manager.get_session_lock(session_id)
    async with lock:
        # Only session lock needed (no processor lock!)

        # Call stateless processor (no mutation)
        result = await processor.observe(
            observation=data,
            session_state=session,
            config=session.session_config
        )

        # Update session with new state
        session.stm = result['stm']
        session.emotives_accumulator = result['emotives_accumulator']
        session.metadata_accumulator = result['metadata_accumulator']
        session.time = result['time']
        session.percept_data = result['percept_data']
        session.predictions = result['predictions']

        await session_manager.update_session(session)

    return ObservationResult(
        status=result['status'],
        session_id=session_id,
        stm_length=len(result['stm']),
        time=result['time'],
        unique_id=result['unique_id'],
        auto_learned_pattern=result.get('auto_learned_pattern')
    )
```

### 7 Endpoints to Update

1. **observe_in_session** (line ~299)
   - Remove processor lock
   - Pass `session_state=session`
   - Update session from result dict

2. **learn_in_session** (line ~440)
   - Remove processor lock
   - Pass `session_state=session`
   - Update `session.stm = result['stm']`

3. **get_session_predictions** (line ~729)
   - Remove processor lock
   - Pass `session_state=session`
   - Return predictions directly

4. **get_session_stm** (line ~405)
   - Remove processor lock from sync block (if any)
   - Just return `session.stm` (already in Redis)

5. **clear_session_stm** (line ~485)
   - Remove processor lock
   - Call `memory_manager.clear_stm(pattern_processor)`
   - Clear session state in Redis

6. **clear_session_all_memory** (line ~508)
   - Remove processor lock
   - Call `memory_manager.clear_all_memory(pattern_processor, vector_processor)`
   - Reset session state in Redis

7. **observe_sequence_in_session** (line ~535)
   - Remove processor lock
   - Pass `session_state=session` to each observe call
   - Update session state after each observation

---

## PHASE 1.9: Remove Processor Locks from processor_manager.py

**File**: `kato/processors/processor_manager.py`

### Remove get_processor_lock() Method (Lines 110-129)

```python
# DELETE THIS METHOD:
def get_processor_lock(self, node_id: str) -> asyncio.Lock:
    """
    Get the lock for a specific processor.
    ...
    """
    processor_id = self._get_processor_id(node_id)
    if processor_id not in self.processor_locks:
        self.processor_locks[processor_id] = asyncio.Lock()
    return self.processor_locks[processor_id]
```

### Keep get_processor() As-Is

The `get_processor()` method still uses locks during **creation** only (which is fine):

```python
async def get_processor(self, node_id: str, ...) -> KatoProcessor:
    # Check cache
    if processor_id in self.processors:
        return processor  # No lock needed for cached access

    # Lock only for creation (this is OK)
    async with self.processor_locks[processor_id]:
        # Double-check and create if needed
        ...
```

This lock is for **processor creation**, not **processor usage**. It's safe to keep.

---

## PHASE 1.10: Remove Processor Locks from sessions.py

**File**: `kato/api/endpoints/sessions.py`

### Find and Remove All These Lines

Search for and DELETE:
```python
processor_lock = app_state.processor_manager.get_processor_lock(session.node_id)
async with processor_lock:
```

### Locations (approximate line numbers)

1. **observe_in_session** (~line 336-337)
2. **learn_in_session** (~line 460-461)
3. **get_session_predictions** (~line 745-747)
4. **get_session_stm** (~line 421-422, if exists)
5. **clear_session_stm** (~line 496-497)
6. **clear_session_all_memory** (~line 519-520)
7. **observe_sequence_in_session** (~line 602-603)

### Indentation Fix

After removing `async with processor_lock:`, **dedent the block** by one level:

```python
# BEFORE:
async with lock:
    processor_lock = ...
    async with processor_lock:  # ❌ DELETE
        # Code here (4 spaces indent)  # ⬅️ DEDENT TO 2 SPACES

# AFTER:
async with lock:
    # Code here (2 spaces indent)  # ✅ DEDENTED
```

---

## TESTING CHECKLIST

After completing all phases:

### Unit Tests
- [ ] Test MemoryManager static methods work correctly
- [ ] Test KatoProcessor observe() with session_state
- [ ] Test KatoProcessor get_predictions() with session_state
- [ ] Test KatoProcessor learn() with session_state

### Integration Tests
- [ ] Run `test_session_isolation_bug.py` - All tests MUST PASS
- [ ] Test concurrent sessions with same node_id (no corruption)
- [ ] Test session config isolation
- [ ] Test STM isolation
- [ ] Test emotives/metadata isolation

### API Tests
- [ ] Test observe_in_session endpoint
- [ ] Test learn_in_session endpoint
- [ ] Test get_session_predictions endpoint
- [ ] Test all 7 session endpoints work

### Performance Tests
- [ ] Measure throughput (observations/second)
- [ ] Compare before/after (expect 5-10x improvement)
- [ ] Test 100 concurrent sessions on same node_id

---

## ROLLBACK PROCEDURE

If anything breaks:

```bash
# Revert to checkpoint
git reset --hard 3dc344d  # Phase 1.1 checkpoint commit

# Or revert specific file
git checkout HEAD -- kato/workers/kato_processor.py
```

---

## EXPECTED OUTCOMES

### Before (Stateful)
- ❌ Session isolation requires locks
- ❌ Sequential processing (concurrency bottleneck)
- ❌ 100 req/sec throughput
- ❌ Race conditions possible

### After (Stateless)
- ✅ Session isolation by design (no locks)
- ✅ True concurrent processing
- ✅ 500-1000 req/sec throughput
- ✅ No race conditions possible

---

## SUPPORT

If you encounter issues:

1. **Check git diff** - See what changed
2. **Run specific test** - Isolate the problem
3. **Review this plan** - Make sure step was followed correctly
4. **Ask for help** - Provide error message and file/line

---

**Document Version**: 1.0
**Created**: 2025-11-25
**Status**: Phase 1.1 Complete, Phase 1.2-1.10 Ready for Implementation
