#!/usr/bin/env python3
"""
Test script to verify kb_id isolation in ClickHouse.

Tests that patterns from different kb_ids (nodes) are completely isolated.
"""

import sys
import clickhouse_connect
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def test_kb_id_isolation():
    """Test kb_id isolation between different nodes."""

    # Connect to ClickHouse
    logger.info("=" * 80)
    logger.info("Testing kb_id Isolation in ClickHouse")
    logger.info("=" * 80)

    client = clickhouse_connect.get_client(
        host='localhost',
        port=8123,
        database='kato'
    )

    try:
        # Clear any existing test data
        logger.info("\n1. Cleaning up existing test data...")
        client.command("ALTER TABLE patterns_data DROP PARTITION 'test_node0'")
        client.command("ALTER TABLE patterns_data DROP PARTITION 'test_node1'")
        logger.info("   ✓ Test partitions cleared")

        # Insert test patterns for node0
        logger.info("\n2. Inserting test patterns for 'test_node0'...")
        node0_data = {
            'kb_id': ['test_node0', 'test_node0', 'test_node0'],
            'name': ['PTRN|node0_pattern1', 'PTRN|node0_pattern2', 'PTRN|node0_pattern3'],
            'pattern_data': [
                [['token1', 'token2']],
                [['token3', 'token4']],
                [['token5', 'token6']]
            ],
            'length': [2, 2, 2],
            'token_set': [['token1', 'token2'], ['token3', 'token4'], ['token5', 'token6']],
            'token_count': [2, 2, 2],
            'minhash_sig': [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            'lsh_bands': [[100, 200], [300, 400], [500, 600]],
            'first_token': ['token1', 'token3', 'token5'],
            'last_token': ['token2', 'token4', 'token6']
        }

        client.insert(
            'patterns_data',
            node0_data.values(),
            column_names=list(node0_data.keys())
        )
        logger.info("   ✓ Inserted 3 patterns for test_node0")

        # Insert test patterns for node1
        logger.info("\n3. Inserting test patterns for 'test_node1'...")
        node1_data = {
            'kb_id': ['test_node1', 'test_node1', 'test_node1'],
            'name': ['PTRN|node1_pattern1', 'PTRN|node1_pattern2', 'PTRN|node1_pattern3'],
            'pattern_data': [
                [['alpha', 'beta']],
                [['gamma', 'delta']],
                [['epsilon', 'zeta']]
            ],
            'length': [2, 2, 2],
            'token_set': [['alpha', 'beta'], ['gamma', 'delta'], ['epsilon', 'zeta']],
            'token_count': [2, 2, 2],
            'minhash_sig': [[10, 20, 30], [40, 50, 60], [70, 80, 90]],
            'lsh_bands': [[1000, 2000], [3000, 4000], [5000, 6000]],
            'first_token': ['alpha', 'gamma', 'epsilon'],
            'last_token': ['beta', 'delta', 'zeta']
        }

        client.insert(
            'patterns_data',
            node1_data.values(),
            column_names=list(node1_data.keys())
        )
        logger.info("   ✓ Inserted 3 patterns for test_node1")

        # Test 1: Query node0 patterns
        logger.info("\n4. Testing kb_id='test_node0' isolation...")
        result_node0 = client.query(
            "SELECT kb_id, name FROM patterns_data WHERE kb_id = 'test_node0' ORDER BY name"
        )

        node0_patterns = [row[1] for row in result_node0.result_rows]
        logger.info(f"   Patterns returned: {node0_patterns}")

        # Verify only node0 patterns
        expected_node0 = ['PTRN|node0_pattern1', 'PTRN|node0_pattern2', 'PTRN|node0_pattern3']
        if node0_patterns == expected_node0:
            logger.info("   ✓ PASS: Only test_node0 patterns returned")
        else:
            logger.error(f"   ✗ FAIL: Expected {expected_node0}, got {node0_patterns}")
            return False

        # Test 2: Query node1 patterns
        logger.info("\n5. Testing kb_id='test_node1' isolation...")
        result_node1 = client.query(
            "SELECT kb_id, name FROM patterns_data WHERE kb_id = 'test_node1' ORDER BY name"
        )

        node1_patterns = [row[1] for row in result_node1.result_rows]
        logger.info(f"   Patterns returned: {node1_patterns}")

        # Verify only node1 patterns
        expected_node1 = ['PTRN|node1_pattern1', 'PTRN|node1_pattern2', 'PTRN|node1_pattern3']
        if node1_patterns == expected_node1:
            logger.info("   ✓ PASS: Only test_node1 patterns returned")
        else:
            logger.error(f"   ✗ FAIL: Expected {expected_node1}, got {node1_patterns}")
            return False

        # Test 3: Verify no cross-contamination
        logger.info("\n6. Verifying no cross-contamination...")

        # Check if node0 query returns any node1 patterns
        cross_check_query = """
        SELECT COUNT(*) as count
        FROM patterns_data
        WHERE kb_id = 'test_node0' AND name LIKE '%node1%'
        """
        cross_result = client.query(cross_check_query)
        cross_count = cross_result.result_rows[0][0]

        if cross_count == 0:
            logger.info("   ✓ PASS: No node1 patterns in node0 query")
        else:
            logger.error(f"   ✗ FAIL: Found {cross_count} node1 patterns in node0 query")
            return False

        # Test 4: Verify partition pruning is working
        logger.info("\n7. Verifying partition pruning...")
        explain_query = "EXPLAIN SELECT * FROM patterns_data WHERE kb_id = 'test_node0'"
        explain_result = client.query(explain_query)
        explain_text = '\n'.join([row[0] for row in explain_result.result_rows])

        if 'test_node0' in explain_text and 'ReadFromMergeTree' in explain_text:
            logger.info("   ✓ PASS: Query plan shows partition pruning")
            logger.info(f"   Query plan (excerpt):\n{explain_text[:500]}...")
        else:
            logger.warning("   ⚠ WARNING: Could not verify partition pruning from query plan")

        # Test 5: Check partition list
        logger.info("\n8. Checking partitions...")
        partitions_query = """
        SELECT partition, rows
        FROM system.parts
        WHERE table = 'patterns_data' AND database = 'kato'
        AND partition IN ('test_node0', 'test_node1')
        GROUP BY partition
        ORDER BY partition
        """
        partitions_result = client.query(partitions_query)

        logger.info("   Active partitions:")
        for row in partitions_result.result_rows:
            partition, rows = row
            logger.info(f"     - {partition}: {rows} rows")

        if len(partitions_result.result_rows) == 2:
            logger.info("   ✓ PASS: Both test partitions exist")
        else:
            logger.error(f"   ✗ FAIL: Expected 2 partitions, found {len(partitions_result.result_rows)}")
            return False

        logger.info("\n" + "=" * 80)
        logger.info("✓ ALL TESTS PASSED: kb_id isolation is working correctly!")
        logger.info("=" * 80)

        # Cleanup
        logger.info("\n9. Cleaning up test data...")
        client.command("ALTER TABLE patterns_data DROP PARTITION 'test_node0'")
        client.command("ALTER TABLE patterns_data DROP PARTITION 'test_node1'")
        logger.info("   ✓ Test partitions cleaned up")

        return True

    except Exception as e:
        logger.error(f"\n✗ TEST FAILED WITH ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        client.close()


if __name__ == '__main__':
    success = test_kb_id_isolation()
    sys.exit(0 if success else 1)
