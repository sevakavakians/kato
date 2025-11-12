#!/usr/bin/env python3
"""
Diagnostic script to check pattern storage in test databases.

This script checks MongoDB databases created during tests to verify that
patterns are being stored correctly. It checks both the expected database
names and the processor_id-suffixed names.
"""

import sys
from pymongo import MongoClient
from collections import defaultdict


def diagnose_test_databases():
    """Check all test databases for pattern storage."""

    # Connect to MongoDB
    client = MongoClient('mongodb://localhost:27017')

    # Get all database names
    all_dbs = client.list_database_names()
    test_dbs = [db for db in all_dbs if 'test_' in db.lower()]

    print("=" * 80)
    print("KATO Test Database Pattern Storage Diagnostic")
    print("=" * 80)
    print(f"\nFound {len(test_dbs)} test databases\n")

    # Statistics
    stats = {
        'total_dbs': 0,
        'dbs_with_patterns': 0,
        'dbs_without_patterns': 0,
        'total_patterns': 0,
        'dbs_with_symbols': 0,
        'total_symbols': 0
    }

    # Check each test database
    results = []
    for db_name in sorted(test_dbs):
        stats['total_dbs'] += 1
        db = client[db_name]

        # Check collections exist
        collections = db.list_collection_names()
        has_patterns_kb = 'patterns_kb' in collections
        has_symbols_kb = 'symbols_kb' in collections

        # Count patterns
        pattern_count = 0
        symbol_count = 0
        metadata_totals = {}

        if has_patterns_kb:
            pattern_count = db.patterns_kb.count_documents({})
            if pattern_count > 0:
                stats['dbs_with_patterns'] += 1
                stats['total_patterns'] += pattern_count
            else:
                stats['dbs_without_patterns'] += 1

        if has_symbols_kb:
            symbol_count = db.symbols_kb.count_documents({})
            if symbol_count > 0:
                stats['dbs_with_symbols'] += 1
                stats['total_symbols'] += symbol_count

        # Check metadata totals
        if 'metadata' in collections:
            totals_doc = db.metadata.find_one({'class': 'totals'})
            if totals_doc:
                metadata_totals = {
                    'total_pattern_frequencies': totals_doc.get('total_pattern_frequencies', 0),
                    'total_symbol_frequencies': totals_doc.get('total_symbol_frequencies', 0),
                    'total_symbols_in_patterns_frequencies': totals_doc.get('total_symbols_in_patterns_frequencies', 0)
                }

        results.append({
            'db_name': db_name,
            'pattern_count': pattern_count,
            'symbol_count': symbol_count,
            'metadata_totals': metadata_totals,
            'has_collections': has_patterns_kb and has_symbols_kb
        })

    # Print detailed results
    print("Database Analysis:")
    print("-" * 80)

    for result in results:
        db_name = result['db_name']
        pattern_count = result['pattern_count']
        symbol_count = result['symbol_count']
        metadata = result['metadata_totals']

        # Color coding
        status = "✓" if pattern_count > 0 else "✗"

        print(f"\n{status} {db_name}")
        print(f"   Patterns: {pattern_count}")
        print(f"   Symbols: {symbol_count}")

        if metadata:
            print(f"   Metadata totals:")
            print(f"     - Pattern frequencies: {metadata.get('total_pattern_frequencies', 0)}")
            print(f"     - Symbol frequencies: {metadata.get('total_symbol_frequencies', 0)}")
            print(f"     - Symbols in patterns: {metadata.get('total_symbols_in_patterns_frequencies', 0)}")

        # Check for potential database name issues
        if pattern_count == 0 and result['has_collections']:
            # Look for related databases with suffixes
            base_name = db_name.replace('_kato', '')
            related_dbs = [d for d in test_dbs if d.startswith(base_name) and d != db_name]
            if related_dbs:
                print(f"   ⚠️  Warning: Found related databases: {related_dbs}")

    # Print summary statistics
    print("\n" + "=" * 80)
    print("Summary Statistics:")
    print("-" * 80)
    print(f"Total test databases: {stats['total_dbs']}")
    print(f"Databases with patterns: {stats['dbs_with_patterns']}")
    print(f"Databases without patterns: {stats['dbs_without_patterns']}")
    print(f"Total patterns across all databases: {stats['total_patterns']}")
    print(f"Databases with symbols: {stats['dbs_with_symbols']}")
    print(f"Total symbols across all databases: {stats['total_symbols']}")

    # Analysis
    print("\n" + "=" * 80)
    print("Analysis:")
    print("-" * 80)

    if stats['dbs_without_patterns'] > 0:
        print(f"⚠️  {stats['dbs_without_patterns']} test databases have NO patterns stored!")
        print("   This indicates that pattern learning is not working correctly.")
        print("   Possible causes:")
        print("   1. Database name mismatch (processor_id suffix issue)")
        print("   2. Write concern not being applied (patterns not persisted)")
        print("   3. learn() method failing silently")
        print("   4. Tests not actually calling learn()")

    if stats['total_patterns'] > 0:
        print(f"✓ {stats['total_patterns']} total patterns found across {stats['dbs_with_patterns']} databases")
        print("  Some tests are successfully storing patterns.")

    # Database name pattern analysis
    print("\n" + "=" * 80)
    print("Database Naming Pattern Analysis:")
    print("-" * 80)

    kato_suffix_dbs = [db for db in test_dbs if db.endswith('_kato')]
    print(f"Databases with '_kato' suffix: {len(kato_suffix_dbs)}")

    for db_name in kato_suffix_dbs[:5]:  # Show first 5 examples
        pattern_count = next(r['pattern_count'] for r in results if r['db_name'] == db_name)
        print(f"  - {db_name}: {pattern_count} patterns")

    print("\n" + "=" * 80)

    return stats


if __name__ == '__main__':
    try:
        stats = diagnose_test_databases()

        # Exit with error code if issues found
        if stats['dbs_without_patterns'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"Error running diagnostic: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)
