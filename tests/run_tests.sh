#!/bin/bash

# Script to run KATO tests with proper setup

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}KATO Test Runner${NC}"
echo "=================="

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

# Install dependencies if needed
if [ "$1" == "--install" ] || [ ! -d "venv" ]; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    # Remove old venv if it exists
    if [ -d "venv" ]; then
        rm -rf venv 2>/dev/null || mv venv venv_old_$(date +%s) 2>/dev/null
    fi
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate 2>/dev/null || {
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
    }
fi

# Ensure KATO is built
echo -e "${YELLOW}Building KATO Docker image...${NC}"
../kato-manager.sh build

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

# Run tests based on type
echo -e "${GREEN}Running $TEST_TYPE tests...${NC}"
echo ""

case $TEST_TYPE in
    unit)
        pytest tests/unit/ $VERBOSE $PARALLEL
        ;;
    integration)
        pytest tests/integration/ $VERBOSE $PARALLEL
        ;;
    api)
        pytest tests/api/ $VERBOSE $PARALLEL
        ;;
    all)
        pytest tests/ $VERBOSE $PARALLEL
        ;;
esac

TEST_RESULT=$?

# Deactivate virtual environment
deactivate

# Report results
echo ""
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Tests passed successfully!${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
fi

exit $TEST_RESULT