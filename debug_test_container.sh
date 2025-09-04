#!/bin/bash

# Debug script to inspect test container environment

echo "=== Debugging Test Container ==="

# Start a KATO instance for testing
echo "Starting KATO instance..."
PROCESSOR_ID=debug_test_$$
PROCESSOR_NAME=DebugTest

PROCESSOR_ID="$PROCESSOR_ID" PROCESSOR_NAME="$PROCESSOR_NAME" ./kato-manager.sh start >/dev/null 2>&1

echo "KATO started with processor ID: $PROCESSOR_ID"

# Run test container interactively to debug
echo ""
echo "Running test container to inspect environment..."
docker run --rm \
    --network kato-network \
    -e KATO_CLUSTER_MODE=true \
    -e KATO_TEST_MODE=container \
    -e KATO_PROCESSOR_ID="$PROCESSOR_ID" \
    -e KATO_API_URL="http://kato-${PROCESSOR_ID}:8000" \
    -e VERBOSE_OUTPUT=true \
    -v "${PWD}/tests:/tests:ro" \
    kato-test-harness:latest \
    /bin/bash -c "
echo '=== Container Environment ==='
echo 'Python version:' && python3 --version
echo ''
echo 'Pytest version:' && python3 -m pytest --version
echo ''
echo 'Test directory structure:'
ls -la /tests/tests/ | head -10
echo ''
echo 'Unit test files:'
ls -la /tests/tests/unit/*.py | head -5
echo ''
echo 'Checking if test file exists:'
ls -la /tests/tests/unit/test_observations.py
echo ''
echo 'Trying to collect tests from test_observations.py:'
cd /tests && python3 -m pytest tests/unit/test_observations.py --collect-only 2>&1 | head -20
echo ''
echo 'Checking Python path:'
python3 -c 'import sys; print(\"\\n\".join(sys.path))'
echo ''
echo 'Checking if tests module can be imported:'
python3 -c 'import tests.tests.unit.test_observations' 2>&1 | head -10
echo ''
echo 'List actual test functions in file:'
grep '^def test_' /tests/tests/unit/test_observations.py | head -5
"

# Cleanup
echo ""
echo "Cleaning up..."
./kato-manager.sh stop "$PROCESSOR_ID" >/dev/null 2>&1

echo "Debug complete!"