#!/bin/bash

# KATO Test Log Rotation Script
# Manages test log files to prevent disk space issues

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEST_OUTPUT_DIR="${SCRIPT_DIR}/test-runs"

# Configuration
MAX_AGE_DAYS=7          # Delete logs older than this
COMPRESS_AGE_DAYS=1     # Compress logs older than this
MAX_RUNS_TO_KEEP=20     # Maximum number of test runs to keep
MAX_SIZE_MB=100         # Alert if total size exceeds this

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to get directory size in MB
get_dir_size_mb() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        # Use du with -m for megabytes, handle both GNU and BSD du
        local size_mb=$(du -sm "$dir" 2>/dev/null | cut -f1)
        echo "${size_mb:-0}"
    else
        echo "0"
    fi
}

# Function to rotate logs
rotate_logs() {
    log_info "Starting log rotation in $TEST_OUTPUT_DIR"
    
    # Check if directory exists
    if [[ ! -d "$TEST_OUTPUT_DIR" ]]; then
        log_warning "Test output directory does not exist: $TEST_OUTPUT_DIR"
        exit 0
    fi
    
    # Count files before rotation
    local count_before=$(find "$TEST_OUTPUT_DIR" -name "test-*.log*" -o -name "test-*.txt*" 2>/dev/null | wc -l)
    log_info "Found $count_before log files before rotation"
    
    # Delete old logs
    log_info "Deleting logs older than $MAX_AGE_DAYS days..."
    find "$TEST_OUTPUT_DIR" -name "test-*.log*" -mtime +$MAX_AGE_DAYS -delete 2>/dev/null || true
    find "$TEST_OUTPUT_DIR" -name "test-*.txt*" -mtime +$MAX_AGE_DAYS -delete 2>/dev/null || true
    
    # Compress logs older than COMPRESS_AGE_DAYS
    log_info "Compressing logs older than $COMPRESS_AGE_DAYS days..."
    find "$TEST_OUTPUT_DIR" -name "test-*.log" -mtime +$COMPRESS_AGE_DAYS ! -name "*.gz" -exec gzip {} \; 2>/dev/null || true
    
    # Keep only MAX_RUNS_TO_KEEP most recent runs
    log_info "Keeping only $MAX_RUNS_TO_KEEP most recent test runs..."
    
    # For each type of file, keep only the most recent ones
    for pattern in "test-output-*.log*" "test-summary-*.txt*" "test-errors-*.log*"; do
        local files=$(ls -t "$TEST_OUTPUT_DIR"/$pattern 2>/dev/null | tail -n +$((MAX_RUNS_TO_KEEP + 1)))
        if [[ -n "$files" ]]; then
            echo "$files" | xargs rm -f 2>/dev/null || true
        fi
    done
    
    # Count files after rotation
    local count_after=$(find "$TEST_OUTPUT_DIR" -name "test-*.log*" -o -name "test-*.txt*" 2>/dev/null | wc -l)
    log_info "Have $count_after log files after rotation"
    
    # Check total size
    local total_size_mb=$(get_dir_size_mb "$TEST_OUTPUT_DIR")
    if [[ $total_size_mb -gt $MAX_SIZE_MB ]]; then
        log_warning "Test logs directory size ($total_size_mb MB) exceeds limit ($MAX_SIZE_MB MB)"
        log_warning "Consider reducing MAX_RUNS_TO_KEEP or MAX_AGE_DAYS"
    else
        log_info "Test logs directory size: $total_size_mb MB (limit: $MAX_SIZE_MB MB)"
    fi
    
    # Clean up broken symlinks in latest directory
    if [[ -d "$TEST_OUTPUT_DIR/latest" ]]; then
        log_info "Cleaning up broken symlinks..."
        find "$TEST_OUTPUT_DIR/latest" -type l ! -exec test -e {} \; -delete 2>/dev/null || true
    fi
    
    log_success "Log rotation completed (removed $((count_before - count_after)) files)"
}

# Function to show statistics
show_stats() {
    log_info "Test Log Statistics"
    echo "==================="
    
    if [[ ! -d "$TEST_OUTPUT_DIR" ]]; then
        log_warning "Test output directory does not exist"
        return
    fi
    
    # Count different types of files
    local output_logs=$(find "$TEST_OUTPUT_DIR" -name "test-output-*.log*" 2>/dev/null | wc -l)
    local summary_files=$(find "$TEST_OUTPUT_DIR" -name "test-summary-*.txt*" 2>/dev/null | wc -l)
    local error_logs=$(find "$TEST_OUTPUT_DIR" -name "test-errors-*.log*" 2>/dev/null | wc -l)
    local compressed=$(find "$TEST_OUTPUT_DIR" -name "*.gz" 2>/dev/null | wc -l)
    
    echo "Output logs:    $output_logs"
    echo "Summary files:  $summary_files"
    echo "Error logs:     $error_logs"
    echo "Compressed:     $compressed"
    echo ""
    
    # Show size information
    local total_size_mb=$(get_dir_size_mb "$TEST_OUTPUT_DIR")
    echo "Total size:     $total_size_mb MB"
    echo ""
    
    # Show most recent test run
    local latest_output=$(ls -t "$TEST_OUTPUT_DIR"/test-output-*.log* 2>/dev/null | head -1)
    if [[ -n "$latest_output" ]]; then
        echo "Most recent test run:"
        echo "  $(basename "$latest_output")"
        echo "  Modified: $(date -r "$latest_output" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || stat -f "%Sm" "$latest_output" 2>/dev/null || echo "unknown")"
    fi
}

# Parse command line arguments
case "${1:-rotate}" in
    rotate)
        rotate_logs
        ;;
    stats)
        show_stats
        ;;
    clean)
        log_warning "Removing ALL test logs..."
        rm -rf "$TEST_OUTPUT_DIR"/*
        log_success "All test logs removed"
        ;;
    help)
        echo "KATO Test Log Rotation Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  rotate  - Rotate logs according to policy (default)"
        echo "  stats   - Show log statistics"
        echo "  clean   - Remove all test logs"
        echo "  help    - Show this help message"
        echo ""
        echo "Configuration:"
        echo "  Max age: $MAX_AGE_DAYS days"
        echo "  Compress after: $COMPRESS_AGE_DAYS days"
        echo "  Keep runs: $MAX_RUNS_TO_KEEP"
        echo "  Size alert: $MAX_SIZE_MB MB"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac