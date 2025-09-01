#!/bin/bash

# Check if Docker containers need rebuilding based on source file changes
# Returns 0 if rebuild needed, 1 if not needed

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
KATO_IMAGE="kato:latest"
TEST_HARNESS_IMAGE="kato-test-harness:latest"
BUILD_MARKER_DIR="${SCRIPT_DIR}/.build-markers"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1" >&2; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# Create build marker directory if it doesn't exist
mkdir -p "$BUILD_MARKER_DIR"

# Function to get Docker image build time
get_image_build_time() {
    local image="$1"
    local build_time
    
    # Check if image exists
    if ! docker images "$image" --format "{{.CreatedAt}}" | head -1 | grep -q .; then
        echo "0"  # Image doesn't exist
        return
    fi
    
    # Get the image creation timestamp in epoch format
    build_time=$(docker inspect "$image" 2>/dev/null | \
        python3 -c "
import sys, json, datetime
try:
    data = json.load(sys.stdin)
    if data and len(data) > 0:
        created = data[0].get('Created', '')
        if created:
            # Handle ISO format with Z timezone
            dt = datetime.datetime.fromisoformat(created.replace('Z', '+00:00'))
            print(int(dt.timestamp()))
        else:
            print(0)
    else:
        print(0)
except:
    print(0)" 2>/dev/null || echo "0")
    
    echo "$build_time"
}

# Function to find newest file in a directory pattern
find_newest_file() {
    local pattern="$1"
    local newest_time=0
    
    # Find all files matching pattern and get the newest modification time
    while IFS= read -r file; do
        if [[ -f "$file" ]]; then
            file_time=$(stat -f "%m" "$file" 2>/dev/null || stat -c "%Y" "$file" 2>/dev/null || echo "0")
            if [[ $file_time -gt $newest_time ]]; then
                newest_time=$file_time
            fi
        fi
    done < <(find . -type f -path "$pattern" 2>/dev/null)
    
    echo "$newest_time"
}

# Check KATO image rebuild necessity
check_kato_rebuild() {
    local kato_build_time=$(get_image_build_time "$KATO_IMAGE")
    local needs_rebuild=false
    local newest_source_time=0
    local newest_file=""
    
    log_info "Checking KATO image rebuild necessity..."
    
    if [[ "$kato_build_time" == "0" ]]; then
        log_warning "KATO image not found or invalid"
        echo "true"
        return
    fi
    
    # Check Python files in kato/
    local kato_py_time=$(find_newest_file "./kato/*.py")
    if [[ $kato_py_time -gt $newest_source_time ]]; then
        newest_source_time=$kato_py_time
        newest_file="kato/*.py"
    fi
    
    # Check all subdirectories in kato/
    for dir in kato/*/; do
        if [[ -d "$dir" ]]; then
            local dir_time=$(find_newest_file "./${dir}*.py")
            if [[ $dir_time -gt $newest_source_time ]]; then
                newest_source_time=$dir_time
                newest_file="${dir}*.py"
            fi
        fi
    done
    
    # Check shell scripts
    local sh_time=$(find_newest_file "./*.sh")
    if [[ $sh_time -gt $newest_source_time ]]; then
        newest_source_time=$sh_time
        newest_file="*.sh"
    fi
    
    # Check Dockerfile
    if [[ -f "Dockerfile" ]]; then
        local dockerfile_time=$(stat -f "%m" "Dockerfile" 2>/dev/null || stat -c "%Y" "Dockerfile" 2>/dev/null || echo "0")
        if [[ $dockerfile_time -gt $newest_source_time ]]; then
            newest_source_time=$dockerfile_time
            newest_file="Dockerfile"
        fi
    fi
    
    # Check requirements.txt
    if [[ -f "requirements.txt" ]]; then
        local req_time=$(stat -f "%m" "requirements.txt" 2>/dev/null || stat -c "%Y" "requirements.txt" 2>/dev/null || echo "0")
        if [[ $req_time -gt $newest_source_time ]]; then
            newest_source_time=$req_time
            newest_file="requirements.txt"
        fi
    fi
    
    # Check setup.py
    if [[ -f "setup.py" ]]; then
        local setup_time=$(stat -f "%m" "setup.py" 2>/dev/null || stat -c "%Y" "setup.py" 2>/dev/null || echo "0")
        if [[ $setup_time -gt $newest_source_time ]]; then
            newest_source_time=$setup_time
            newest_file="setup.py"
        fi
    fi
    
    # Compare times
    if [[ $newest_source_time -gt $kato_build_time ]]; then
        log_warning "KATO image is outdated (newest file: $newest_file)"
        log_info "Image built: $(date -r $kato_build_time 2>/dev/null || date -d @$kato_build_time 2>/dev/null || echo 'unknown')"
        log_info "Source updated: $(date -r $newest_source_time 2>/dev/null || date -d @$newest_source_time 2>/dev/null || echo 'unknown')"
        echo "true"
    else
        log_info "KATO image is up to date"
        echo "false"
    fi
}

# Check test harness rebuild necessity
check_test_harness_rebuild() {
    local harness_build_time=$(get_image_build_time "$TEST_HARNESS_IMAGE")
    local needs_rebuild=false
    local newest_source_time=0
    local newest_file=""
    
    log_info "Checking test harness image rebuild necessity..."
    
    if [[ "$harness_build_time" == "0" ]]; then
        log_warning "Test harness image not found or invalid"
        echo "true"
        return
    fi
    
    # Check test files
    local test_py_time=$(find_newest_file "./tests/*.py")
    if [[ $test_py_time -gt $newest_source_time ]]; then
        newest_source_time=$test_py_time
        newest_file="tests/*.py"
    fi
    
    # Check all subdirectories in tests/
    for dir in tests/*/; do
        if [[ -d "$dir" ]]; then
            local dir_time=$(find_newest_file "./${dir}*.py")
            if [[ $dir_time -gt $newest_source_time ]]; then
                newest_source_time=$dir_time
                newest_file="${dir}*.py"
            fi
        fi
    done
    
    # Check kato source (since it's mounted in test container)
    local kato_time=$(find_newest_file "./kato/*.py")
    if [[ $kato_time -gt $newest_source_time ]]; then
        newest_source_time=$kato_time
        newest_file="kato/*.py"
    fi
    
    # Check Dockerfile.test
    if [[ -f "Dockerfile.test" ]]; then
        local dockerfile_time=$(stat -f "%m" "Dockerfile.test" 2>/dev/null || stat -c "%Y" "Dockerfile.test" 2>/dev/null || echo "0")
        if [[ $dockerfile_time -gt $newest_source_time ]]; then
            newest_source_time=$dockerfile_time
            newest_file="Dockerfile.test"
        fi
    fi
    
    # Check requirements-test.txt
    if [[ -f "requirements-test.txt" ]]; then
        local req_time=$(stat -f "%m" "requirements-test.txt" 2>/dev/null || stat -c "%Y" "requirements-test.txt" 2>/dev/null || echo "0")
        if [[ $req_time -gt $newest_source_time ]]; then
            newest_source_time=$req_time
            newest_file="requirements-test.txt"
        fi
    fi
    
    # Check test-harness.sh itself
    if [[ -f "test-harness.sh" ]]; then
        local harness_sh_time=$(stat -f "%m" "test-harness.sh" 2>/dev/null || stat -c "%Y" "test-harness.sh" 2>/dev/null || echo "0")
        if [[ $harness_sh_time -gt $newest_source_time ]]; then
            newest_source_time=$harness_sh_time
            newest_file="test-harness.sh"
        fi
    fi
    
    # Compare times
    if [[ $newest_source_time -gt $harness_build_time ]]; then
        log_warning "Test harness image is outdated (newest file: $newest_file)"
        log_info "Image built: $(date -r $harness_build_time 2>/dev/null || date -d @$harness_build_time 2>/dev/null || echo 'unknown')"
        log_info "Source updated: $(date -r $newest_source_time 2>/dev/null || date -d @$newest_source_time 2>/dev/null || echo 'unknown')"
        echo "true"
    else
        log_info "Test harness image is up to date"
        echo "false"
    fi
}

# Main logic
main() {
    local check_type="${1:-all}"
    local kato_needs_rebuild="false"
    local harness_needs_rebuild="false"
    
    case "$check_type" in
        kato)
            kato_needs_rebuild=$(check_kato_rebuild)
            if [[ "$kato_needs_rebuild" == "true" ]]; then
                exit 0  # Rebuild needed
            fi
            ;;
        test-harness|harness)
            harness_needs_rebuild=$(check_test_harness_rebuild)
            if [[ "$harness_needs_rebuild" == "true" ]]; then
                exit 0  # Rebuild needed
            fi
            ;;
        all|*)
            kato_needs_rebuild=$(check_kato_rebuild)
            harness_needs_rebuild=$(check_test_harness_rebuild)
            
            if [[ "$kato_needs_rebuild" == "true" ]] || [[ "$harness_needs_rebuild" == "true" ]]; then
                log_warning "Container rebuild needed:"
                [[ "$kato_needs_rebuild" == "true" ]] && log_warning "  - KATO image needs rebuild"
                [[ "$harness_needs_rebuild" == "true" ]] && log_warning "  - Test harness image needs rebuild"
                exit 0  # Rebuild needed
            fi
            ;;
    esac
    
    log_info "All containers are up to date"
    exit 1  # No rebuild needed
}

# Run main function
main "$@"