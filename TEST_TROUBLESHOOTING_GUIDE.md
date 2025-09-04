# KATO Test Troubleshooting Guide

This guide documents the systematic troubleshooting process for fixing test failures in KATO.

## Core Troubleshooting Process

### Step 1: Manual API Testing First
Before diving into test code, understand what the system ACTUALLY does:

```bash
# Start a KATO instance manually
./kato-manager.sh start

# Test APIs directly with curl
curl -X POST http://localhost:8000/kato-instance/observe \
  -H "Content-Type: application/json" \
  -d '{"strings": ["hello"], "vectors": [], "emotives": {}}'

# Save responses to compare with test expectations
curl ... | jq '.' > actual_response.json
```

**Key Learnings to Document:**
- Exact request format required (which fields are mandatory?)
- Actual response structure (what fields are returned?)
- Error messages and status codes
- Behavioral quirks (e.g., emotives MUST be a dictionary, not array)

### Step 2: Compare Manual vs Test Behavior
Run the same operations that failing tests perform:

1. **Extract test operations**: Read the failing test to understand what it's doing
2. **Reproduce manually**: Execute the same sequence of API calls manually
3. **Compare results**: 
   ```bash
   # What the test expects
   grep "assert" test_file.py
   
   # What actually happens
   cat actual_response.json
   ```
4. **Document discrepancies**: Note differences between expectations and reality

### Step 3: Root Cause Analysis
Trace back to understand WHY there's a mismatch:

#### Questions to Ask:
- What does the documentation say about the expectation?
- Is the documentation ambiguous or does it not address this behavior? If so, stop and ask clarifying questions.
- Is this a test assumption problem or actual code bug?
- Has the API behavior changed but tests weren't updated?
- Is there a configuration difference between test and manual environments?
- Are there timing/race conditions?
- Is the test using the wrong endpoint or parameters?

#### Investigation Tools:
```bash
# Check container logs
docker logs kato-api-$(whoami)-1 --tail 50

# Monitor in real-time
docker logs -f kato-api-$(whoami)-1

# Check MongoDB for actual data
docker exec mongodb-$(whoami)-1 mongosh --eval "db.patterns_kb.find()"

# Verify ZMQ communication
docker exec kato-api-$(whoami)-1 python3 -c "import socket; s = socket.socket(); s.settimeout(1); result = s.connect_ex(('localhost', 5555)); print('ZMQ port 5555 is', 'open' if result == 0 else 'closed')"
```

### Step 4: Fix Infrastructure First, Then Logic

#### Priority Order:
1. **Container/Build Issues** - Can't test if containers won't build
   ```bash
   # Check if rebuild needed
   ./check-rebuild-needed.sh
   
   # Rebuild if necessary
   ./kato-manager.sh build
   ./test-harness.sh build
   ```

2. **Script/Configuration Issues** - Tests must be able to run
   - Fix syntax errors in test scripts
   - Ensure proper file permissions (`chmod +x`)
   - Fix import errors and missing dependencies

3. **Test Infrastructure** - Framework must work correctly
   - Fix fixtures that don't initialize properly
   - Resolve test isolation issues (processor_id uniqueness)
   - Fix cluster orchestration problems

4. **Test Logic** - Finally, fix actual test expectations
   - Update assertions to match actual behavior
   - Add tolerance for approximate calculations
   - Fix incorrect test assumptions

### Step 5: Incremental Testing
Build confidence gradually:

```bash
# 1. Test single function/endpoint
python3 -m pytest tests/test_file.py::test_specific_function -v

# 2. Test single file
./test-harness.sh test tests/tests/unit/test_specific_file.py

# 3. Test category
./test-harness.sh suite unit

# 4. Run full suite only after smaller tests pass
./kato-manager.sh test
```

## Common Patterns and Solutions

### Pattern 1: "KeyError" in API Calls
**Symptom**: 500 error, KeyError in logs
**Cause**: Missing required field in request
**Solution**: 
```python
# Bad: Missing required fields
requests.post(url, json={"strings": ["test"]})

# Good: All required fields present
requests.post(url, json={"strings": ["test"], "vectors": [], "emotives": {}})
```

### Pattern 2: Test Expects Exact Value, Gets Approximate
**Symptom**: Assertion fails on float comparison
**Cause**: Heuristic calculations return approximations
**Solution**:
```python
# Bad: Exact comparison
assert similarity == 0.5

# Good: Tolerance-based comparison
assert abs(similarity - 0.5) < 0.1  # Allow 10% tolerance
# Or
assert similarity >= 0.45 and similarity <= 0.55
```

### Pattern 3: Pattern Not Found
**Symptom**: get_pattern returns 404
**Cause**: Pattern name format mismatch
**Solution**:
```python
# MongoDB stores without prefix
db_pattern = "a5b9c3d7e1f2..."

# API returns with prefix
api_pattern = "PTRN|a5b9c3d7e1f2..."

# Strip prefix when querying
pattern_hash = pattern_name.replace("PTRN|", "")
```

### Pattern 4: No Predictions Returned
**Symptom**: Empty predictions array when expecting results
**Cause**: Insufficient data or threshold too high
**Solution**:
```python
# Ensure minimum 2 strings in STM
observe(["first"])
observe(["second"])  # Now predictions can be generated

# Check recall_threshold isn't filtering everything
set_recall_threshold(0.1)  # More permissive

# Verify at least one symbol matches
# Patterns with NO matches are NEVER returned
```

## Quick Debugging Checklist

- [ ] Is KATO running? (`./kato-manager.sh status`)
- [ ] Are all required services up? (`docker ps`)
- [ ] Is the test using the correct processor_id?
- [ ] Are all required API fields present?
- [ ] Is the test checking for exact values where approximations are used?
- [ ] Has the code changed but containers not rebuilt?
- [ ] Is there enough data in STM for predictions (2+ strings)?
- [ ] Is recall_threshold appropriate for the test case?
- [ ] Are test fixtures properly initialized and cleaned up?
- [ ] Is test isolation working (unique processor_ids)?

## Test-Specific Debugging Commands

```bash
# See what's in short-term memory
curl http://localhost:8000/kato-instance/short-term-memory | jq

# Check current genes/configuration
curl http://localhost:8000/kato-instance/genes | jq

# Get all predictions with details
curl http://localhost:8000/kato-instance/predictions | jq

# Check pattern in MongoDB directly
docker exec mongodb-$(whoami)-1 mongosh processor_id --eval "db.patterns_kb.findOne({sha1_hash: 'hash_here'})"

# View recent API calls in logs
docker logs kato-api-$(whoami)-1 --tail 20 | grep -E "(POST|GET)"
```

## When to Escalate

Consider these actual code bugs (not test issues) if:
1. Manual testing confirms unexpected behavior
2. The behavior violates documented specifications
3. Multiple independent tests fail the same way
4. The issue affects production use cases

## Critical Architecture Issue: No Processor Isolation

**BREAKING DISCOVERY**: The REST gateway ignores processor_id in URL paths. This means:
- URLs like `/proc1/observe` and `/proc2/observe` all route to the SAME instance
- Tests cannot achieve isolation through different processor_ids
- All tests share the same KATO memory and state
- This causes tests to fail when run together but pass in isolation

**Evidence** (in `rest_gateway.py`):
```python
processor_id = self.path.split('/')[1]  # Extracted but never used
response = pool.execute('observe', observation_data)  # No processor_id passed
```

**Workaround**:
1. ALWAYS call `clear_all_memory()` at test start
2. Don't run tests in parallel
3. Accept that tests may contaminate each other

## Remember

1. **Don't assume the test is correct** - It might have wrong expectations
2. **Heuristics mean approximations** - Don't test for exact decimal values
3. **Check the basics first** - Is the service running? Is the data there?
4. **Document your findings** - Update tests AND documentation when behavior is clarified
5. **Test isolation is BROKEN** - Processor_ids don't work, all tests share same instance

## Success Metrics

You know you've properly fixed a test when:
- ✅ Test passes consistently (not flaky)
- ✅ Manual verification confirms the behavior
- ✅ Documentation matches the implementation
- ✅ No other tests broken by your fix
- ✅ The fix makes logical sense (not just a hack)
