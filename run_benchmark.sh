#!/bin/bash

# KATO Performance Benchmark Script
# Compares different optimization configurations

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "KATO Performance Benchmark"
echo "=========================================="
echo ""

# Function to run benchmark with specific configuration
run_benchmark() {
    local config_name=$1
    local use_optimized=$2
    local use_fast_matching=$3
    local use_indexing=$4
    
    echo "Configuration: $config_name"
    echo "  KATO_USE_OPTIMIZED=$use_optimized"
    echo "  KATO_USE_FAST_MATCHING=$use_fast_matching"
    echo "  KATO_USE_INDEXING=$use_indexing"
    echo "---"
    
    # Export environment variables
    export KATO_USE_OPTIMIZED=$use_optimized
    export KATO_USE_FAST_MATCHING=$use_fast_matching
    export KATO_USE_INDEXING=$use_indexing
    
    # Run the standalone optimization test
    if [ -f "tests/test_optimizations_standalone.py" ]; then
        python3 tests/test_optimizations_standalone.py 2>&1 | grep -E "(Speedup:|✓|Performance:|ms)" || true
    fi
    
    # Run determinism tests to ensure correctness
    echo ""
    echo "Checking determinism..."
    python3 -m pytest tests/tests/unit/test_determinism_preservation.py -q --tb=no 2>&1 | tail -1 || true
    
    echo ""
    echo "=========================================="
    echo ""
}

# Check if specific config requested
if [ "$1" == "--original" ]; then
    echo "Running ORIGINAL implementation only"
    echo ""
    run_benchmark "Original Implementation" "false" "false" "false"
    
elif [ "$1" == "--optimized" ]; then
    echo "Running FULLY OPTIMIZED implementation only"
    echo ""
    run_benchmark "Fully Optimized" "true" "true" "true"
    
elif [ "$1" == "--quick" ]; then
    echo "Running quick comparison (original vs fully optimized)"
    echo ""
    run_benchmark "Original Implementation" "false" "false" "false"
    run_benchmark "Fully Optimized" "true" "true" "true"
    
else
    echo "Running complete benchmark suite"
    echo "Use --original, --optimized, or --quick for specific tests"
    echo ""
    
    # Test 1: Original implementation (baseline)
    run_benchmark "Original Implementation (Baseline)" "false" "false" "false"
    
    # Test 2: Optimized structure only
    run_benchmark "Optimized Structure Only" "true" "false" "false"
    
    # Test 3: Optimized with fast matching
    run_benchmark "Optimized + Fast Matching" "true" "true" "false"
    
    # Test 4: Fully optimized
    run_benchmark "Fully Optimized (All Features)" "true" "true" "true"
    
    echo "=========================================="
    echo "BENCHMARK COMPLETE"
    echo ""
    echo "Summary:"
    echo "- Original: Baseline implementation"
    echo "- Optimized Structure: New architecture, original algorithms"
    echo "- Fast Matching: New architecture + fast algorithms"
    echo "- Fully Optimized: All optimizations enabled"
    echo "=========================================="
fi

# Cleanup
unset KATO_USE_OPTIMIZED
unset KATO_USE_FAST_MATCHING
unset KATO_USE_INDEXING