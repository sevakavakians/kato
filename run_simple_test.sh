#!/bin/bash

# Simple test runner for KATO
# Runs tests directly with a single KATO instance

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Generate unique processor ID
PROCESSOR_ID="test_$(date +%s)_$$"
PROCESSOR_NAME="SimpleTest"

# Function to cleanup
cleanup() {
    log_info "Cleaning up test instance..."
    ./kato-manager.sh stop "$PROCESSOR_ID" >/dev/null 2>&1 || true
    log_success "Cleanup complete"
}

# Set trap for cleanup
trap cleanup EXIT

# Parse arguments
TEST_PATH="${1:-tests/tests/unit/}"
VERBOSE="${2:-}"

log_info "Starting KATO instance for testing..."
log_info "Processor ID: $PROCESSOR_ID"

# Start KATO instance with dedicated databases
PROCESSOR_ID="$PROCESSOR_ID" PROCESSOR_NAME="$PROCESSOR_NAME" ./kato-manager.sh start >/dev/null 2>&1

# Wait for KATO to be ready
log_info "Waiting for KATO to be ready..."
MAX_WAIT=30
WAITED=0
while [[ $WAITED -lt $MAX_WAIT ]]; do
    if curl -s "http://localhost:8000/kato-api/ping" >/dev/null 2>&1; then
        log_success "KATO is ready"
        break
    fi
    sleep 1
    ((WAITED++))
done

if [[ $WAITED -eq $MAX_WAIT ]]; then
    log_error "KATO failed to start"
    exit 1
fi

# Verify all services
log_info "Verifying services..."
./kato-manager.sh verify "$PROCESSOR_ID" | grep -E "✓|✗|⚠" || true

# Set environment for tests
export KATO_PROCESSOR_ID="$PROCESSOR_ID"
export KATO_API_URL="http://localhost:8000"
export KATO_TEST_MODE="local"

# Run tests
log_info "Running tests: $TEST_PATH"
echo "=================================================="

if [[ "$VERBOSE" == "-v" ]] || [[ "$VERBOSE" == "--verbose" ]]; then
    python3 -m pytest "$TEST_PATH" -v --tb=short --color=yes
else
    python3 -m pytest "$TEST_PATH" --tb=short --color=yes -q
fi

TEST_EXIT_CODE=$?

echo "=================================================="

# Show summary
if [[ $TEST_EXIT_CODE -eq 0 ]]; then
    log_success "All tests passed!"
else
    log_warning "Some tests failed (exit code: $TEST_EXIT_CODE)"
fi

exit $TEST_EXIT_CODE