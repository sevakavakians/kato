#!/bin/bash
# Quick test of a single test to verify everything works

set -e

# Start KATO instance
echo "Starting KATO instance..."
PROCESSOR_ID="quicktest_$$"
PROCESSOR_NAME="QuickTest"

PROCESSOR_ID="$PROCESSOR_ID" PROCESSOR_NAME="$PROCESSOR_NAME" ./kato-manager.sh start >/dev/null 2>&1

echo "Running single test in container..."
docker run --rm \
    --network kato-network \
    -e KATO_CLUSTER_MODE=true \
    -e KATO_TEST_MODE=container \
    -e KATO_PROCESSOR_ID="$PROCESSOR_ID" \
    -e KATO_API_URL="http://kato-${PROCESSOR_ID}:8000" \
    -v "${PWD}/tests:/tests:ro" \
    kato-test-harness:latest \
    bash -c "cd /tests && python3 -m pytest tests/unit/test_observations.py::test_observe_single_string -v"

# Cleanup
echo "Cleaning up..."
./kato-manager.sh stop "$PROCESSOR_ID" >/dev/null 2>&1

echo "Test complete!"