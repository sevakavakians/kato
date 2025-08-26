#!/bin/bash

# Script to run KATO tests with proper setup

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}KATO Test Runner${NC}"
echo "=================="

# Set ZMQ implementation to improved for tests
export KATO_ZMQ_IMPLEMENTATION=improved
echo -e "${GREEN}Using improved ZMQ implementation (ROUTER/DEALER)${NC}"

# Check if we're in the right directory
if [ ! -f "pytest.ini" ]; then
    echo -e "${RED}Error: Not in kato-tests directory${NC}"
    echo "Please run this script from the kato-tests directory"
    exit 1
fi

# Check if venv needs to be recreated (if it points to old path)
if [ -f "venv/pyvenv.cfg" ]; then
    if grep -q "kato-tests-v2" venv/pyvenv.cfg; then
        echo -e "${YELLOW}Virtual environment points to old path, recreating...${NC}"
        rm -rf venv 2>/dev/null || mv venv venv_old_$(date +%s) 2>/dev/null
    fi
fi

# Skip virtual environment complications - use system Python3
echo -e "${GREEN}Using system Python3 and pytest${NC}"

# Ensure KATO Docker image exists
if [[ -z $(docker images -q kato:latest 2> /dev/null) ]]; then
    echo -e "${YELLOW}KATO Docker image not found. Building...${NC}"
    ../kato-manager.sh build
else
    echo -e "${GREEN}KATO Docker image already exists${NC}"
fi

# Set Python path
export PYTHONPATH="$(pwd):$(pwd)/tests:${PYTHONPATH}"

# Parse test options
TEST_TYPE="all"
VERBOSE=""
PARALLEL=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            TEST_TYPE="unit"
            shift
            ;;
        --integration)
            TEST_TYPE="integration"
            shift
            ;;
        --api)
            TEST_TYPE="api"
            shift
            ;;
        --verbose|-v)
            VERBOSE="-vv"
            shift
            ;;
        --parallel|-n)
            PARALLEL="-n auto"
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [options]"
            echo ""
            echo "Options:"
            echo "  --unit          Run only unit tests"
            echo "  --integration   Run only integration tests"
            echo "  --api           Run only API tests"
            echo "  --verbose, -v   Verbose output"
            echo "  --parallel, -n  Run tests in parallel"
            echo "  --install       Force reinstall dependencies"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                    # Run all tests"
            echo "  ./run_tests.sh --unit             # Run only unit tests"
            echo "  ./run_tests.sh --unit --verbose   # Run unit tests with verbose output"
            echo "  ./run_tests.sh --parallel         # Run tests in parallel"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Run tests based on type using system Python3
echo -e "${GREEN}Running $TEST_TYPE tests...${NC}"
echo ""

case $TEST_TYPE in
    unit)
        python3 -m pytest tests/unit/ $VERBOSE $PARALLEL
        ;;
    integration)
        python3 -m pytest tests/integration/ $VERBOSE $PARALLEL
        ;;
    api)
        python3 -m pytest tests/api/ $VERBOSE $PARALLEL
        ;;
    all)
        python3 -m pytest tests/ $VERBOSE $PARALLEL
        ;;
esac

TEST_RESULT=$?

# Report results
echo ""
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Tests passed successfully!${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
fi

exit $TEST_RESULT