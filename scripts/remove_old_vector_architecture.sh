#!/bin/bash

# Script to remove old vector architecture from KATO
# This removes the legacy CVCSearcher and related code

set -e

echo "========================================="
echo "KATO Old Vector Architecture Removal"
echo "========================================="
echo ""
echo "This script will remove:"
echo "1. Legacy CVCSearcher class from vector_searches.py"
echo "2. MongoDB vector-specific code (keeping general MongoDB support)"
echo "3. Old multiprocessing-based vector search code"
echo ""
echo "WARNING: This is a breaking change!"
echo "Make sure you have:"
echo "- Tested the new vector architecture thoroughly"
echo "- Migrated all vectors to Qdrant"
echo "- Updated all code to use CVCSearcherModern"
echo ""
read -p "Are you sure you want to proceed? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Creating backup..."
cp kato/searches/vector_searches.py kato/searches/vector_searches.py.backup
echo "✓ Backup created: kato/searches/vector_searches.py.backup"

echo ""
echo "Removing old vector architecture code..."

# Create new vector_searches.py with only modern code
cat > kato/searches/vector_searches.py << 'EOF'
"""
Vector Searches Module (Modernized)

This module now only contains utility functions for vector operations.
The main vector search functionality has been moved to vector_search_engine.py
"""

import logging
from os import environ

try:
    from numpy.linalg import norm
except ImportError:
    # Fallback if numpy is not properly installed
    def norm(x):
        return sum(i**2 for i in x) ** 0.5

logger = logging.getLogger('kato.searches.classification')
logger.setLevel(getattr(logging, environ['LOG_LEVEL']))
logger.info('logging initiated')


def calculate_diff_lengths(vector_x, vector_y, func=norm, diff=None):
    """
    Calculate the difference and lengths of two vectors.
    
    Args:
        vector_x: First vector
        vector_y: Second vector
        func: Function to calculate vector length (default: norm)
        diff: Pre-calculated difference (optional)
    
    Returns:
        Tuple of (difference_length, x_length, y_length, difference_vector)
    """
    if diff is None:
        diff = vector_x - vector_y
    
    diff_length = func(diff)
    x_length = func(vector_x)
    y_length = func(vector_y)
    
    return diff_length, x_length, y_length, diff


# For backward compatibility, import CVCSearcherModern as CVCSearcher
from kato.searches.vector_search_engine import CVCSearcherModern as CVCSearcher

__all__ = ['CVCSearcher', 'calculate_diff_lengths']
EOF

echo "✓ Removed legacy CVCSearcher implementation"
echo "✓ Added compatibility alias (CVCSearcher -> CVCSearcherModern)"

echo ""
echo "Updating imports in other files..."

# Update any direct imports of CVCSearcher
find kato -name "*.py" -type f | while read file; do
    if grep -q "from.*vector_searches import.*CVCSearcher" "$file"; then
        echo "  Updating: $file"
        sed -i.bak 's/from.*vector_searches import.*CVCSearcher/from kato.searches.vector_search_engine import CVCSearcherModern as CVCSearcher/g' "$file"
        rm "${file}.bak"
    fi
done

echo ""
echo "Removing old test files for legacy architecture..."
if [ -f "tests/test_vector_multiprocessing.py" ]; then
    mv tests/test_vector_multiprocessing.py tests/test_vector_multiprocessing.py.backup
    echo "✓ Backed up: tests/test_vector_multiprocessing.py"
fi

echo ""
echo "========================================="
echo "✅ Old Vector Architecture Removed!"
echo "========================================="
echo ""
echo "Summary of changes:"
echo "- Legacy CVCSearcher removed"
echo "- Compatibility alias added (CVCSearcher -> CVCSearcherModern)"
echo "- Imports updated across codebase"
echo "- Backup files created with .backup extension"
echo ""
echo "Next steps:"
echo "1. Rebuild Docker image: ./kato-manager.sh build"
echo "2. Restart KATO: ./kato-manager.sh restart"
echo "3. Run tests to verify: python3 tests/test_vector_simplified.py"
echo ""
echo "To restore if needed:"
echo "  cp kato/searches/vector_searches.py.backup kato/searches/vector_searches.py"