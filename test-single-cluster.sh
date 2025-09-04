#!/bin/bash
# Quick test of a single cluster to verify everything works

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[INFO]${NC} Testing single cluster to verify setup..."

# Create a minimal test cluster definition
cat > /tmp/test_single_cluster.py << 'EOF'
from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class TestCluster:
    name: str
    config: Dict[str, Any]
    test_patterns: List[str]
    description: str

TEST_CLUSTERS = [
    TestCluster(
        name="quick_test",
        config={
            "recall_threshold": 0.1,
            "max_pattern_length": 0
        },
        test_patterns=[
            "test_observations.py::test_single_observation",
        ],
        description="Quick test to verify setup"
    ),
]
EOF

# Temporarily replace the test clusters file
cp tests/tests/fixtures/test_clusters.py tests/tests/fixtures/test_clusters.py.bak
cp /tmp/test_single_cluster.py tests/tests/fixtures/test_clusters.py

# Run the test
export VERBOSE=true
./cluster-orchestrator.sh run

# Restore original file
mv tests/tests/fixtures/test_clusters.py.bak tests/tests/fixtures/test_clusters.py

echo -e "${GREEN}[SUCCESS]${NC} Single cluster test complete!"