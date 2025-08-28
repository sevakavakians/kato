#\!/bin/bash

# Run KATO tests with optimization flags
# This script ensures the flags are properly set for testing

echo "=================================="
echo "KATO Optimized Tests Runner"
echo "=================================="
echo ""

# Set optimization flags
export KATO_USE_OPTIMIZED=true
export KATO_USE_FAST_MATCHING=true
export KATO_USE_INDEXING=true

# Set required environment variables
export LOG_LEVEL=INFO

echo "Optimization flags set:"
echo "  KATO_USE_OPTIMIZED=$KATO_USE_OPTIMIZED"
echo "  KATO_USE_FAST_MATCHING=$KATO_USE_FAST_MATCHING"
echo "  KATO_USE_INDEXING=$KATO_USE_INDEXING"
echo ""

# Check if we should run specific tests
if [ "$1" == "performance" ]; then
    echo "Running performance tests only..."
    python3 -m pytest tests/tests/performance/ -v
elif [ "$1" == "unit" ]; then
    echo "Running unit tests only..."
    python3 -m pytest tests/tests/unit/ -v
elif [ "$1" == "integration" ]; then
    echo "Running integration tests only..."
    python3 -m pytest tests/tests/integration/ -v
elif [ "$1" == "api" ]; then
    echo "Running API tests only..."
    python3 -m pytest tests/tests/api/ -v
else
    echo "Running all tests..."
    python3 -m pytest tests/ -v
fi
