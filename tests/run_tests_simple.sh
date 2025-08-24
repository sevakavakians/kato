#!/bin/bash

# Simple KATO test runner without virtual environment complications
# Uses system Python3 and pytest

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}KATO Simple Test Runner${NC}"
echo "======================="
echo ""

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if we're in the right directory
if [ ! -f "$SCRIPT_DIR/pytest.ini" ]; then
    echo -e "${RED}Error: pytest.ini not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# Change to the test directory
cd "$SCRIPT_DIR"

# Set Python path
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/tests:${PYTHONPATH}"

# Ensure KATO is built
echo -e "${YELLOW}Building KATO Docker image...${NC}"
../kato-manager.sh build

echo ""
echo -e "${GREEN}Running tests from: $SCRIPT_DIR${NC}"
echo ""

# Parse arguments
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
            echo "Usage: ./run_tests_simple.sh [options]"
            echo ""
            echo "Options:"
            echo "  --unit          Run only unit tests"
            echo "  --integration   Run only integration tests"
            echo "  --api           Run only API tests"
            echo "  --verbose, -v   Verbose output"
            echo "  --parallel, -n  Run tests in parallel"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# Run tests based on type
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