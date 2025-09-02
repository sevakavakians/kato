"""
Test clustering definitions for KATO test isolation.
Groups tests by their configuration requirements to minimize instance creation.
"""

from typing import Dict, List, Any
from dataclasses import dataclass
import os


@dataclass
class TestCluster:
    """Represents a cluster of tests with shared configuration."""
    name: str
    config: Dict[str, Any]
    test_patterns: List[str]
    description: str


# Define test clusters based on configuration requirements
TEST_CLUSTERS = [
    TestCluster(
        name="default",
        config={
            "recall_threshold": 0.1,
            "max_pattern_length": 0
        },
        test_patterns=[
            "tests/unit/test_observations.py",
            "tests/unit/test_pattern_hashing.py", 
            "tests/unit/test_sorting_behavior.py",
            "tests/unit/test_determinism_preservation.py",
            "tests/unit/test_edge_cases_comprehensive.py",
            "tests/unit/test_minimum_pattern_requirement.py",
            "tests/unit/test_prediction_fields.py",
            "tests/unit/test_predictions.py",
            "tests/unit/test_prediction_edge_cases.py",
            "tests/unit/test_comprehensive_patterns.py",
            # test_memory_management.py moved to separate clusters for specific tests
            "tests/api/test_rest_endpoints.py",
            # test_pattern_learning.py moved to separate clusters for specific tests
            "tests/integration/test_vector_e2e.py",
            "tests/integration/test_vector_simplified.py",
            "tests/performance/test_vector_stress.py"
        ],
        description="Tests using default KATO configuration"
    ),
    
    TestCluster(
        name="recall_dynamic",
        config={
            "recall_threshold": 0.1,  # Tests will change this as needed
            "max_pattern_length": 0
        },
        test_patterns=[
            # Include full files so all tests run
            "tests/unit/test_recall_threshold_values.py",
            "tests/unit/test_recall_threshold_patterns.py",
            "tests/unit/test_recall_threshold_edge_cases.py",
        ],
        description="Tests that dynamically change recall threshold during execution"
    ),
    
    TestCluster(
        name="memory_general",
        config={
            "recall_threshold": 0.1,
            "max_pattern_length": 0
        },
        test_patterns=[
            # All memory management tests except test_max_pattern_length
            "tests/unit/test_memory_management.py",
        ],
        description="General memory management tests"
    ),
    
    TestCluster(
        name="pattern_learning_general",
        config={
            "recall_threshold": 0.1,
            "max_pattern_length": 0
        },
        test_patterns=[
            # All pattern learning tests except test_max_pattern_length_auto_learn
            "tests/integration/test_pattern_learning.py",
        ],
        description="General pattern learning integration tests"
    ),
    
    TestCluster(
        name="auto_learning",
        config={
            "recall_threshold": 0.1,
            "max_pattern_length": 3
        },
        test_patterns=[
            # Only specific tests that require max_pattern_length
            "tests/unit/test_memory_management.py::test_max_pattern_length",
            "tests/integration/test_pattern_learning.py::test_max_pattern_length_auto_learn",
        ],
        description="Tests requiring auto-learning enabled with max_pattern_length"
    )
]


def get_cluster_for_test(test_path: str) -> TestCluster:
    """
    Determine which cluster a test belongs to.
    
    Args:
        test_path: Path to the test file or test function
        
    Returns:
        The appropriate TestCluster for the test
    """
    # Normalize the test path
    test_file = os.path.basename(test_path).split("::")[0]
    
    # Check each cluster's patterns
    for cluster in TEST_CLUSTERS:
        for pattern in cluster.test_patterns:
            # Check if pattern matches the test file
            if pattern in test_path or test_file == pattern:
                return cluster
            # Check for test function matches
            if "::" in pattern and pattern in test_path:
                return cluster
    
    # Default to the default cluster
    return TEST_CLUSTERS[0]


def get_tests_for_cluster(cluster: TestCluster, test_dir: str) -> List[str]:
    """
    Get all test files that belong to a cluster.
    
    Args:
        cluster: The test cluster
        test_dir: Directory containing tests
        
    Returns:
        List of test file paths for the cluster
    """
    test_files = []
    
    for pattern in cluster.test_patterns:
        # Handle specific test function patterns
        if "::" in pattern:
            test_files.append(pattern)
        else:
            # Find matching test files
            for root, _, files in os.walk(test_dir):
                for file in files:
                    if file == pattern:
                        rel_path = os.path.relpath(os.path.join(root, file), test_dir)
                        test_files.append(rel_path)
    
    return test_files


def requires_configuration_change(test_path: str) -> bool:
    """
    Check if a test requires configuration changes during execution.
    
    Args:
        test_path: Path to the test
        
    Returns:
        True if the test changes configuration during execution
    """
    # Tests in the mixed_recall cluster change configuration
    mixed_cluster = next((c for c in TEST_CLUSTERS if c.name == "mixed_recall"), None)
    if mixed_cluster:
        test_file = os.path.basename(test_path).split("::")[0]
        return any(pattern in test_path or test_file == pattern 
                   for pattern in mixed_cluster.test_patterns)
    return False