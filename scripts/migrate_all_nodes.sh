#!/bin/bash
# Multi-Node MongoDB → ClickHouse/Redis Migration Script
#
# Migrates pattern data from multiple MongoDB databases (nodes) to
# ClickHouse and Redis for hybrid architecture deployment.
#
# Usage:
#   ./scripts/migrate_all_nodes.sh [--dry-run] [--nodes "node0 node1 node2"] [--batch-size 1000]
#
# Options:
#   --dry-run         Test migration without writing to ClickHouse/Redis
#   --nodes           Space-separated list of node names (default: "node0 node1 node2 node3")
#   --batch-size      Number of patterns per batch (default: 1000)
#   --mongo-host      MongoDB host:port (default: localhost:27017)
#   --clickhouse-host ClickHouse host (default: localhost)
#   --redis-host      Redis host (default: localhost)
#   --skip-clickhouse Skip ClickHouse migration
#   --skip-redis      Skip Redis migration
#
# Examples:
#   # Dry run for all nodes
#   ./scripts/migrate_all_nodes.sh --dry-run
#
#   # Migrate only node0 and node1
#   ./scripts/migrate_all_nodes.sh --nodes "node0 node1"
#
#   # Migrate with larger batch size
#   ./scripts/migrate_all_nodes.sh --batch-size 5000

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
NODES=("node0" "node1" "node2" "node3")
MONGO_HOST="localhost:27017"
CLICKHOUSE_HOST="localhost"
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB="kato"
REDIS_HOST="localhost"
REDIS_PORT=6379
BATCH_SIZE=1000
DRY_RUN=""
SKIP_CLICKHOUSE=false
SKIP_REDIS=false

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --nodes)
            IFS=' ' read -r -a NODES <<< "$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --mongo-host)
            MONGO_HOST="$2"
            shift 2
            ;;
        --clickhouse-host)
            CLICKHOUSE_HOST="$2"
            shift 2
            ;;
        --redis-host)
            REDIS_HOST="$2"
            shift 2
            ;;
        --skip-clickhouse)
            SKIP_CLICKHOUSE=true
            shift
            ;;
        --skip-redis)
            SKIP_REDIS=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--dry-run] [--nodes \"node0 node1\"] [--batch-size 1000]"
            exit 1
            ;;
    esac
done

# Print configuration
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Multi-Node Migration Configuration${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Nodes:             ${NODES[*]}"
echo -e "MongoDB:           ${MONGO_HOST}"
echo -e "ClickHouse:        ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/${CLICKHOUSE_DB}"
echo -e "Redis:             ${REDIS_HOST}:${REDIS_PORT}"
echo -e "Batch size:        ${BATCH_SIZE}"
echo -e "Dry run:           ${DRY_RUN:-false}"
echo -e "Skip ClickHouse:   ${SKIP_CLICKHOUSE}"
echo -e "Skip Redis:        ${SKIP_REDIS}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if scripts exist
if [ ! -f "scripts/migrate_mongodb_to_clickhouse.py" ]; then
    echo -e "${RED}Error: scripts/migrate_mongodb_to_clickhouse.py not found${NC}"
    exit 1
fi

if [ ! -f "scripts/migrate_mongodb_to_redis.py" ]; then
    echo -e "${RED}Error: scripts/migrate_mongodb_to_redis.py not found${NC}"
    exit 1
fi

# Statistics
TOTAL_PATTERNS_CLICKHOUSE=0
TOTAL_PATTERNS_REDIS=0
FAILED_NODES=()
START_TIME=$(date +%s)

# Migrate each node
for node in "${NODES[@]}"; do
    echo ""
    echo -e "${GREEN}====================================${NC}"
    echo -e "${GREEN}Migrating node: ${node}${NC}"
    echo -e "${GREEN}====================================${NC}"

    NODE_START_TIME=$(date +%s)

    # ClickHouse migration
    if [ "$SKIP_CLICKHOUSE" = false ]; then
        echo -e "${YELLOW}[ClickHouse] Starting migration for ${node}...${NC}"

        if /usr/local/opt/python@3.10/bin/python3.10 scripts/migrate_mongodb_to_clickhouse.py \
            --mongo-url "mongodb://$MONGO_HOST/$node" \
            --clickhouse-host "$CLICKHOUSE_HOST" \
            --clickhouse-port "$CLICKHOUSE_PORT" \
            --clickhouse-db "$CLICKHOUSE_DB" \
            --batch-size "$BATCH_SIZE" \
            $DRY_RUN; then

            echo -e "${GREEN}[ClickHouse] ✓ Migration successful for ${node}${NC}"
        else
            echo -e "${RED}[ClickHouse] ✗ Migration failed for ${node}${NC}"
            FAILED_NODES+=("$node (ClickHouse)")
        fi
    else
        echo -e "${YELLOW}[ClickHouse] Skipped for ${node}${NC}"
    fi

    echo ""

    # Redis migration
    if [ "$SKIP_REDIS" = false ]; then
        echo -e "${YELLOW}[Redis] Starting migration for ${node}...${NC}"

        if /usr/local/opt/python@3.10/bin/python3.10 scripts/migrate_mongodb_to_redis.py \
            --mongo-url "mongodb://$MONGO_HOST/$node" \
            --redis-host "$REDIS_HOST" \
            --redis-port "$REDIS_PORT" \
            --batch-size "$BATCH_SIZE" \
            $DRY_RUN; then

            echo -e "${GREEN}[Redis] ✓ Migration successful for ${node}${NC}"
        else
            echo -e "${RED}[Redis] ✗ Migration failed for ${node}${NC}"
            FAILED_NODES+=("$node (Redis)")
        fi
    else
        echo -e "${YELLOW}[Redis] Skipped for ${node}${NC}"
    fi

    NODE_END_TIME=$(date +%s)
    NODE_DURATION=$((NODE_END_TIME - NODE_START_TIME))
    echo -e "${BLUE}[${node}] Migration completed in ${NODE_DURATION}s${NC}"
done

# Calculate total duration
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

# Print summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Migration Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Total nodes processed: ${#NODES[@]}"
echo -e "Total duration:        ${TOTAL_DURATION}s"

if [ ${#FAILED_NODES[@]} -eq 0 ]; then
    echo -e "${GREEN}Status: All migrations completed successfully!${NC}"
else
    echo -e "${RED}Status: ${#FAILED_NODES[@]} migration(s) failed:${NC}"
    for failed_node in "${FAILED_NODES[@]}"; do
        echo -e "${RED}  - ${failed_node}${NC}"
    done
fi

echo -e "${BLUE}========================================${NC}"
echo ""

# Verification section (only if not dry run)
if [ -z "$DRY_RUN" ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Verification${NC}"
    echo -e "${BLUE}========================================${NC}"

    # Check ClickHouse
    if [ "$SKIP_CLICKHOUSE" = false ]; then
        echo -e "${YELLOW}Checking ClickHouse...${NC}"
        if command -v docker &> /dev/null; then
            CLICKHOUSE_COUNT=$(docker exec kato-clickhouse clickhouse-client --query \
                "SELECT COUNT(*) FROM kato.patterns_data" 2>/dev/null || echo "ERROR")

            if [ "$CLICKHOUSE_COUNT" != "ERROR" ]; then
                echo -e "${GREEN}✓ ClickHouse: ${CLICKHOUSE_COUNT} patterns${NC}"
            else
                echo -e "${RED}✗ ClickHouse: Unable to query${NC}"
            fi
        else
            echo -e "${YELLOW}  Docker not available, skipping verification${NC}"
        fi
    fi

    # Check Redis
    if [ "$SKIP_REDIS" = false ]; then
        echo -e "${YELLOW}Checking Redis...${NC}"
        if command -v docker &> /dev/null; then
            REDIS_KEYS=$(docker exec kato-redis redis-cli DBSIZE 2>/dev/null | awk '{print $2}' || echo "ERROR")

            if [ "$REDIS_KEYS" != "ERROR" ]; then
                echo -e "${GREEN}✓ Redis: ${REDIS_KEYS} keys${NC}"
            else
                echo -e "${RED}✗ Redis: Unable to query${NC}"
            fi
        else
            echo -e "${YELLOW}  Docker not available, skipping verification${NC}"
        fi
    fi

    echo -e "${BLUE}========================================${NC}"
    echo ""

    # Next steps
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Next Steps${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo -e "1. Switch to hybrid mode:"
    echo -e "   ${YELLOW}./start.sh mode hybrid${NC}"
    echo -e ""
    echo -e "2. Test hybrid architecture:"
    echo -e "   ${YELLOW}python -m pytest tests/tests/integration/test_hybrid_architecture_e2e.py -v${NC}"
    echo -e ""
    echo -e "3. Check logs for hybrid mode:"
    echo -e "   ${YELLOW}./start.sh logs kato | grep -i hybrid${NC}"
    echo -e "${BLUE}========================================${NC}"
fi

# Exit with appropriate code
if [ ${#FAILED_NODES[@]} -eq 0 ]; then
    exit 0
else
    exit 1
fi
