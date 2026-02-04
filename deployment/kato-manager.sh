#!/bin/bash
# KATO Deployment Manager
# Manage KATO services for production deployment

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get container image with version
get_container_image() {
    local container_name=$1
    if docker inspect "$container_name" > /dev/null 2>&1; then
        local image_tag=$(docker inspect --format='{{.Config.Image}}' "$container_name" 2>/dev/null)
        local version=""

        # Try to get version from image labels first
        version=$(docker inspect --format='{{index .Config.Labels "org.opencontainers.image.version"}}' "$container_name" 2>/dev/null)

        # If no label or dev version, try container-specific version commands
        if [[ -z "$version" || "$version" == "<no value>" || "$version" == "dev" ]]; then
            case "$container_name" in
                kato-clickhouse)
                    version=$(docker exec "$container_name" clickhouse-client --version 2>/dev/null | sed -n 's/.*version \([0-9.]*\).*/\1/p' | head -1)
                    ;;
                kato-redis)
                    version=$(docker exec "$container_name" redis-server --version 2>/dev/null | sed -n 's/.*v=\([0-9.]*\).*/\1/p' | head -1)
                    ;;
                kato-qdrant)
                    version=$(curl -s http://localhost:6333/ 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' | head -1)
                    ;;
                kato)
                    # Try to read from kato package __version__
                    version=$(docker exec "$container_name" python -c "from kato import __version__; print(__version__)" 2>/dev/null)
                    if [[ -z "$version" ]]; then
                        # Try to extract from image tag if it's a version tag
                        version=$(echo "$image_tag" | sed -n 's/.*:\([0-9][0-9.]*\).*/\1/p')
                    fi
                    ;;
                kato-dashboard)
                    # Try to extract from image tag if it's a version tag
                    version=$(echo "$image_tag" | sed -n 's/.*:\([0-9][0-9.]*\).*/\1/p')
                    if [[ -z "$version" ]]; then
                        version=$(docker inspect --format='{{index .Config.Labels "version"}}' "$container_name" 2>/dev/null)
                    fi
                    ;;
            esac
        fi

        if [[ -n "$version" && "$version" != "<no value>" && "$version" != "dev" ]]; then
            # Remove leading 'v' if present to avoid double 'v'
            version="${version#v}"
            echo "${image_tag} → v${version}"
        else
            local image_id=$(docker inspect --format='{{.Image}}' "$container_name" 2>/dev/null | cut -d: -f2 | cut -c1-12)
            echo "${image_tag} [${image_id}]"
        fi
    else
        echo "not running"
    fi
}

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Available services
ALL_SERVICES="clickhouse redis qdrant kato dashboard"

# Command to execute
COMMAND=${1:-help}
SERVICE=${2:-all}

# Validate service name
validate_service() {
    if [[ "$1" != "all" ]] && [[ ! " $ALL_SERVICES " =~ " $1 " ]]; then
        print_error "Invalid service: $1"
        print_info "Valid services: $ALL_SERVICES"
        exit 1
    fi
}

case "$COMMAND" in
    start)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Starting all KATO services..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d
            print_info "Waiting for services to be ready..."
            sleep 5

            # Check health
            if curl -s http://localhost:8000/health > /dev/null; then
                print_info "✓ KATO service is healthy"
                print_info "Access KATO at: http://localhost:8000"
                print_info "API Documentation: http://localhost:8000/docs"
            else
                print_warn "Service may still be starting up..."
            fi
        else
            print_info "Starting $SERVICE..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d "$SERVICE"
            print_info "$SERVICE started"
        fi
        ;;

    stop)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Stopping all KATO services..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" down
            print_info "All services stopped"
        else
            print_info "Stopping $SERVICE..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" stop "$SERVICE"
            print_info "$SERVICE stopped"
        fi
        ;;

    restart)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Restarting all KATO services..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" restart
            print_info "All services restarted"
        else
            print_info "Restarting $SERVICE..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" restart "$SERVICE"
            print_info "$SERVICE restarted"
        fi
        ;;

    pull)
        print_info "Pulling latest KATO image from registry..."
        docker pull ghcr.io/sevakavakians/kato:latest
        print_info "Image updated. Run './kato-manager.sh restart kato' to use the new version"
        ;;

    update)
        print_info "Updating KATO to latest version..."
        docker pull ghcr.io/sevakavakians/kato:latest
        print_info "Restarting KATO service..."
        docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d kato
        print_info "✓ KATO updated and restarted"
        ;;

    logs)
        SERVICE=${2:-kato}
        LINES=${3:-50}
        print_info "Showing last $LINES lines of logs for $SERVICE..."
        docker compose -f "$SCRIPT_DIR/docker-compose.yml" logs --tail="$LINES" "$SERVICE"
        ;;

    follow)
        SERVICE=${2:-kato}
        print_info "Following logs for $SERVICE (Ctrl+C to stop)..."
        docker compose -f "$SCRIPT_DIR/docker-compose.yml" logs -f "$SERVICE"
        ;;

    status)
        print_info "Checking service status..."
        docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps

        # Display container images with versions
        echo ""
        print_info "Container Images:"
        printf "  %-20s → %s\n" "kato" "$(get_container_image kato)"
        printf "  %-20s → %s\n" "kato-clickhouse" "$(get_container_image kato-clickhouse)"
        printf "  %-20s → %s\n" "kato-redis" "$(get_container_image kato-redis)"
        printf "  %-20s → %s\n" "kato-qdrant" "$(get_container_image kato-qdrant)"
        printf "  %-20s → %s\n" "kato-dashboard" "$(get_container_image kato-dashboard)"

        # Check KATO health
        echo ""
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            print_info "✓ KATO API is responding"
        else
            print_warn "✗ KATO API is not responding"
        fi

        # Check ClickHouse
        if curl -s http://localhost:8123/ping > /dev/null 2>&1; then
            print_info "✓ ClickHouse is healthy"
        else
            print_warn "✗ ClickHouse is not responding"
            print_info "  Check: docker logs kato-clickhouse --tail 50"
        fi

        # Check Qdrant
        if curl -s http://localhost:6333/health > /dev/null 2>&1; then
            print_info "✓ Qdrant is healthy"
        else
            print_warn "✗ Qdrant is not responding"
        fi

        # Check Redis
        if docker exec kato-redis redis-cli ping > /dev/null 2>&1; then
            print_info "✓ Redis is healthy"
        else
            print_warn "✗ Redis is not responding"
        fi

        # Check Dashboard (optional)
        if curl -s http://localhost:3001/health > /dev/null 2>&1; then
            print_info "✓ Dashboard is healthy (optional)"
        else
            print_warn "✗ Dashboard is not responding (optional - may not be started)"
        fi
        ;;

    clean-data)
        print_warn "⚠️  This will DELETE ALL DATA in ClickHouse, Qdrant, and Redis!"
        print_warn "Services will remain running but all databases will be cleared."
        echo -e "${RED}Are you absolutely sure? (yes/N)${NC}"
        read -r response
        if [[ "$response" == "yes" ]]; then
            print_info "Clearing all database data..."

            # Clear ClickHouse - drop all tables in kato database
            print_info "Clearing ClickHouse database..."
            docker exec kato-clickhouse clickhouse-client --query "DROP DATABASE IF EXISTS kato" || print_error "Failed to drop ClickHouse database"
            docker exec kato-clickhouse clickhouse-client --query "CREATE DATABASE kato" || print_error "Failed to recreate ClickHouse database"

            # Recreate schema from init.sql
            print_info "Recreating ClickHouse schema..."
            if [ -f "$SCRIPT_DIR/config/clickhouse/init.sql" ]; then
                docker exec -i kato-clickhouse clickhouse-client --multiquery < "$SCRIPT_DIR/config/clickhouse/init.sql" || print_error "Failed to recreate schema"
                print_info "✓ Schema recreated successfully"
            else
                print_error "Could not find init.sql at $SCRIPT_DIR/config/clickhouse/init.sql"
                print_warn "You will need to manually recreate the schema before using KATO"
            fi

            # Clear Qdrant - delete all collections
            print_info "Clearing Qdrant collections..."
            COLLECTIONS=$(curl -s -m 10 http://localhost:6333/collections 2>/dev/null | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
            if [ -n "$COLLECTIONS" ]; then
                for collection in $COLLECTIONS; do
                    print_info "Deleting collection: $collection"
                    curl -X DELETE "http://localhost:6333/collections/$collection" 2>/dev/null
                done
            else
                print_info "No Qdrant collections to delete"
            fi

            # Clear Redis - flush all data
            print_info "Clearing Redis data..."
            docker exec kato-redis redis-cli FLUSHALL || print_error "Failed to clear Redis"

            print_info "✓ All database data has been cleared!"
            print_warn "Services are still running. Use './kato-manager.sh restart' if needed."
        else
            print_info "Data cleanup cancelled"
        fi
        ;;

    clean)
        print_warn "This will remove all containers and volumes. Are you sure? (y/N)"
        read -r response
        if [[ "$response" == "y" || "$response" == "Y" ]]; then
            print_info "Cleaning up KATO services..."
            docker compose -f "$SCRIPT_DIR/docker-compose.yml" down -v
            print_info "Cleanup complete"
        else
            print_info "Cleanup cancelled"
        fi
        ;;

    verify)
        print_info "Verifying ClickHouse memory configuration for training workloads..."
        echo ""

        ISSUES_FOUND=0

        # Check if ClickHouse is running
        if ! docker ps --format '{{.Names}}' | grep -q "^kato-clickhouse$"; then
            print_warn "ClickHouse container is not running"
            print_info "Start services with: ./kato-manager.sh start"
            exit 1
        fi

        # Check Docker memory limit
        MEMORY_LIMIT=$(docker inspect kato-clickhouse --format='{{.HostConfig.Memory}}')
        MEMORY_GB=$((MEMORY_LIMIT / 1024 / 1024 / 1024))

        echo -e "${GREEN}✓${NC} Docker Memory Configuration"
        if [ "$MEMORY_LIMIT" -ge 8589934592 ]; then
            echo "  Memory Limit: ${MEMORY_GB}GB (recommended for training)"
        elif [ "$MEMORY_LIMIT" -eq 0 ]; then
            echo -e "  ${YELLOW}⚠${NC} Memory Limit: Unlimited (no docker limit set)"
            print_warn "Recommend setting 8GB limit in docker-compose.yml for stability"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        else
            echo -e "  ${RED}✗${NC} Memory Limit: ${MEMORY_GB}GB (too low for large training)"
            print_error "Recommend increasing to 8GB in docker-compose.yml"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        fi

        # Check ClickHouse effective memory
        CH_MEMORY=$(docker exec kato-clickhouse clickhouse-client --query "SELECT value FROM system.server_settings WHERE name = 'max_server_memory_usage'" 2>/dev/null)
        CH_MEMORY_GB=$((CH_MEMORY / 1024 / 1024 / 1024))
        echo "  ClickHouse Limit: ${CH_MEMORY_GB}GB (90% of container)"
        echo ""

        # Check if expensive logs are disabled
        echo -e "${GREEN}✓${NC} System Log Configuration"

        TRACE_LOG_ENABLED=$(docker exec kato-clickhouse clickhouse-client --query "SELECT count(*) FROM system.tables WHERE database = 'system' AND name = 'trace_log'" 2>/dev/null)
        TEXT_LOG_COUNT=$(docker exec kato-clickhouse clickhouse-client --query "SELECT count(*) FROM system.text_log WHERE event_time > now() - INTERVAL 1 HOUR" 2>/dev/null || echo "0")

        if [ "$TRACE_LOG_ENABLED" -gt 0 ] && [ "$TEXT_LOG_COUNT" -gt 10000 ]; then
            echo -e "  ${RED}✗${NC} Expensive logs are ENABLED (text_log: ${TEXT_LOG_COUNT} msgs/hour)"
            print_error "trace_log and text_log should be disabled in config/clickhouse/logging.xml"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        else
            echo "  trace_log: Disabled or minimal activity ✓"
            echo "  text_log: Disabled or minimal activity ✓"
        fi

        # Check current system log size
        SYSTEM_LOG_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'system' AND active = 1" 2>/dev/null)
        echo "  Current system logs: $SYSTEM_LOG_SIZE"
        echo ""

        # Check query duration filter
        echo -e "${GREEN}✓${NC} Query Logging Filter"
        QUERY_FILTER=$(docker exec kato-clickhouse clickhouse-client --query "SELECT value FROM system.settings WHERE name = 'log_queries_min_query_duration_ms'" 2>/dev/null)
        if [ "$QUERY_FILTER" -ge 1000 ]; then
            echo "  Only logs queries > ${QUERY_FILTER}ms ✓"
        else
            echo -e "  ${YELLOW}⚠${NC} Logs all queries (may accumulate during training)"
            print_warn "Consider setting log_queries_min_query_duration_ms=1000 in config/clickhouse/users.xml"
        fi
        echo ""

        # Check pattern data size
        PATTERN_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'kato' AND table = 'patterns_data' AND active = 1" 2>/dev/null)
        PATTERN_COUNT=$(docker exec kato-clickhouse clickhouse-client --query "SELECT count(*) FROM kato.patterns_data" 2>/dev/null)
        echo -e "${GREEN}✓${NC} Pattern Data"
        echo "  Total patterns: ${PATTERN_COUNT}"
        echo "  Storage size: ${PATTERN_SIZE}"
        echo ""

        # Check Redis configuration
        echo -e "${GREEN}✓${NC} Redis Configuration"

        # Check if Redis is running
        if ! docker ps --format '{{.Names}}' | grep -q "^kato-redis$"; then
            echo -e "  ${RED}✗${NC} Redis container is not running"
            ISSUES_FOUND=$((ISSUES_FOUND + 1))
        else
            # Check Docker memory limit for Redis
            REDIS_MEMORY_LIMIT=$(docker inspect kato-redis --format='{{.HostConfig.Memory}}')
            REDIS_MEMORY_GB=$((REDIS_MEMORY_LIMIT / 1024 / 1024 / 1024))

            if [ "$REDIS_MEMORY_LIMIT" -ge 8589934592 ]; then
                echo "  Docker Memory Limit: ${REDIS_MEMORY_GB}GB ✓"
            elif [ "$REDIS_MEMORY_LIMIT" -eq 0 ]; then
                echo -e "  ${YELLOW}⚠${NC} Docker Memory Limit: Unlimited (no docker limit set)"
                print_warn "Recommend setting 8GB limit in docker-compose.yml"
                ISSUES_FOUND=$((ISSUES_FOUND + 1))
            else
                echo -e "  ${RED}✗${NC} Docker Memory Limit: ${REDIS_MEMORY_GB}GB (recommend 8GB)"
                ISSUES_FOUND=$((ISSUES_FOUND + 1))
            fi

            # Check Redis maxmemory configuration
            REDIS_MAXMEMORY=$(docker exec kato-redis redis-cli CONFIG GET maxmemory 2>/dev/null | tail -1)
            if [ -n "$REDIS_MAXMEMORY" ] && [ "$REDIS_MAXMEMORY" != "0" ]; then
                REDIS_MAXMEMORY_GB=$((REDIS_MAXMEMORY / 1024 / 1024 / 1024))
                echo "  Redis maxmemory: ${REDIS_MAXMEMORY_GB}GB ✓"
            else
                echo -e "  ${YELLOW}⚠${NC} Redis maxmemory: Not set (will use all available memory)"
                print_warn "Recommend setting maxmemory in config/redis.conf"
                ISSUES_FOUND=$((ISSUES_FOUND + 1))
            fi

            # Check eviction policy
            EVICTION_POLICY=$(docker exec kato-redis redis-cli CONFIG GET maxmemory-policy 2>/dev/null | tail -1)
            if [ "$EVICTION_POLICY" = "allkeys-lru" ] || [ "$EVICTION_POLICY" = "volatile-lru" ]; then
                echo "  Eviction policy: $EVICTION_POLICY ✓"
            elif [ "$EVICTION_POLICY" = "noeviction" ]; then
                echo -e "  ${RED}✗${NC} Eviction policy: noeviction (will crash when memory full)"
                print_error "Recommend setting maxmemory-policy to allkeys-lru"
                ISSUES_FOUND=$((ISSUES_FOUND + 1))
            else
                echo "  Eviction policy: $EVICTION_POLICY"
            fi

            # Check persistence configuration
            AOF_ENABLED=$(docker exec kato-redis redis-cli CONFIG GET appendonly 2>/dev/null | tail -1)
            if [ "$AOF_ENABLED" = "yes" ]; then
                echo "  AOF persistence: Enabled ✓"
            else
                echo -e "  ${YELLOW}⚠${NC} AOF persistence: Disabled (risk of data loss)"
            fi
        fi
        echo ""

        # Summary
        if [ $ISSUES_FOUND -eq 0 ]; then
            echo -e "${GREEN}========================================${NC}"
            echo -e "${GREEN}✓ Configuration optimized for training${NC}"
            echo -e "${GREEN}========================================${NC}"
        else
            echo -e "${YELLOW}========================================${NC}"
            echo -e "${YELLOW}⚠ ${ISSUES_FOUND} configuration issue(s) found${NC}"
            echo -e "${YELLOW}========================================${NC}"
            echo ""
            echo "To fix issues:"
            echo "  1. Update docker-compose.yml (set memory: 8G for both services)"
            echo "  2. Mount config/redis.conf in docker-compose.yml"
            echo "  3. Update config/clickhouse/logging.xml (disable text_log, trace_log)"
            echo "  4. Update config/clickhouse/users.xml (set log_queries_min_query_duration_ms)"
            echo "  5. Restart: ./kato-manager.sh restart"
            echo ""
            echo "See: docs/operations/redis-data-protection.md"
        fi
        ;;

    memory)
        # Check if ClickHouse is running
        if ! docker ps --format '{{.Names}}' | grep -q "^kato-clickhouse$"; then
            print_error "ClickHouse container is not running"
            print_info "Start services with: ./kato-manager.sh start"
            exit 1
        fi

        print_info "ClickHouse Memory Usage Report"
        echo ""

        # Get Docker memory limit
        MEMORY_LIMIT=$(docker inspect kato-clickhouse --format='{{.HostConfig.Memory}}')
        MEMORY_LIMIT_GB=$((MEMORY_LIMIT / 1024 / 1024 / 1024))

        # Get current RAM usage from docker stats (one-shot)
        MEMORY_STATS=$(docker stats kato-clickhouse --no-stream --format "{{.MemUsage}}")
        CURRENT_RAM=$(echo "$MEMORY_STATS" | awk '{print $1}')
        MAX_RAM=$(echo "$MEMORY_STATS" | awk '{print $3}')

        # Get ClickHouse server memory setting
        CH_MAX_MEMORY=$(docker exec kato-clickhouse clickhouse-client --query "SELECT value FROM system.server_settings WHERE name = 'max_server_memory_usage'" 2>/dev/null)
        CH_MAX_MEMORY_GB=$((CH_MAX_MEMORY / 1024 / 1024 / 1024))

        # Get current memory usage from ClickHouse metrics
        CH_MEMORY_USAGE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(value) FROM system.asynchronous_metrics WHERE metric = 'MemoryTracking'" 2>/dev/null)
        if [ -z "$CH_MEMORY_USAGE" ]; then
            CH_MEMORY_USAGE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(value) FROM system.metrics WHERE metric = 'MemoryTracking'" 2>/dev/null || echo "N/A")
        fi

        # RAM Usage (Operations)
        echo -e "${GREEN}RAM Usage (Operations):${NC}"
        echo "  Current: $CURRENT_RAM / $MAX_RAM"
        echo "  Container Limit: ${MEMORY_LIMIT_GB}GB"
        echo "  ClickHouse Limit: ${CH_MAX_MEMORY_GB}GB (90% of container)"
        echo "  ClickHouse Tracked: $CH_MEMORY_USAGE"
        echo ""

        # Calculate memory headroom (more robust parsing)
        # Extract numeric values from formats like "1.387GiB" or "280MiB"
        CURRENT_RAM_VALUE=$(echo "$CURRENT_RAM" | grep -oE '[0-9]+\.[0-9]+|[0-9]+' | head -1)
        CURRENT_RAM_UNIT=$(echo "$CURRENT_RAM" | grep -oE 'GiB|MiB|KiB' | head -1)
        MAX_RAM_VALUE=$(echo "$MAX_RAM" | grep -oE '[0-9]+\.[0-9]+|[0-9]+' | head -1)
        MAX_RAM_UNIT=$(echo "$MAX_RAM" | grep -oE 'GiB|MiB|KiB' | head -1)

        # Convert to MB for comparison
        case "$CURRENT_RAM_UNIT" in
            GiB) CURRENT_RAM_MB=$(echo "$CURRENT_RAM_VALUE * 1024" | bc 2>/dev/null || echo "0") ;;
            MiB) CURRENT_RAM_MB=$(echo "$CURRENT_RAM_VALUE" | bc 2>/dev/null || echo "0") ;;
            KiB) CURRENT_RAM_MB=$(echo "$CURRENT_RAM_VALUE / 1024" | bc 2>/dev/null || echo "0") ;;
            *) CURRENT_RAM_MB="0" ;;
        esac

        case "$MAX_RAM_UNIT" in
            GiB) MAX_RAM_MB=$(echo "$MAX_RAM_VALUE * 1024" | bc 2>/dev/null || echo "$((MEMORY_LIMIT_GB * 1024))") ;;
            MiB) MAX_RAM_MB=$(echo "$MAX_RAM_VALUE" | bc 2>/dev/null || echo "$((MEMORY_LIMIT_GB * 1024))") ;;
            KiB) MAX_RAM_MB=$(echo "$MAX_RAM_VALUE / 1024" | bc 2>/dev/null || echo "$((MEMORY_LIMIT_GB * 1024))") ;;
            *) MAX_RAM_MB="$((MEMORY_LIMIT_GB * 1024))" ;;
        esac

        # Ensure we have valid numbers
        CURRENT_RAM_MB=${CURRENT_RAM_MB%.*}  # Remove decimal
        MAX_RAM_MB=${MAX_RAM_MB%.*}

        if [ -z "$CURRENT_RAM_MB" ] || [ "$CURRENT_RAM_MB" = "0" ]; then
            CURRENT_RAM_MB="0"
        fi
        if [ -z "$MAX_RAM_MB" ] || [ "$MAX_RAM_MB" = "0" ]; then
            MAX_RAM_MB="$((MEMORY_LIMIT_GB * 1024))"
        fi

        HEADROOM_MB=$((MAX_RAM_MB - CURRENT_RAM_MB))
        if [ "$MAX_RAM_MB" -gt 0 ]; then
            HEADROOM_PCT=$((100 * HEADROOM_MB / MAX_RAM_MB))
        else
            HEADROOM_PCT=0
        fi

        if [ "$HEADROOM_PCT" -gt 50 ]; then
            echo -e "  Headroom: ${GREEN}${HEADROOM_PCT}% available${NC} (healthy)"
        elif [ "$HEADROOM_PCT" -gt 20 ]; then
            echo -e "  Headroom: ${YELLOW}${HEADROOM_PCT}% available${NC} (monitor closely)"
        else
            echo -e "  Headroom: ${RED}${HEADROOM_PCT}% available${NC} (approaching limit!)"
        fi
        echo ""

        # Disk Usage (Storage)
        echo -e "${GREEN}Disk Usage (Storage):${NC}"

        # Pattern data
        PATTERN_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'kato' AND table = 'patterns_data' AND active = 1" 2>/dev/null || echo "0 B")
        PATTERN_COUNT=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableQuantity(count(*)) FROM kato.patterns_data" 2>/dev/null || echo "0")
        echo "  Pattern Data: $PATTERN_SIZE ($PATTERN_COUNT patterns)"

        # System logs
        SYSTEM_LOG_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'system' AND active = 1" 2>/dev/null || echo "0 B")
        echo "  System Logs: $SYSTEM_LOG_SIZE"

        # Total ClickHouse data
        TOTAL_CH_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE active = 1" 2>/dev/null || echo "0 B")
        echo "  Total ClickHouse: $TOTAL_CH_SIZE"

        # Available disk space
        DISK_AVAILABLE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(free_space) FROM system.disks WHERE name = 'default'" 2>/dev/null || echo "N/A")
        echo "  Available Disk: $DISK_AVAILABLE"
        echo ""

        # Memory breakdown by table (top 5)
        echo -e "${GREEN}Top 5 Tables by Disk Usage:${NC}"
        docker exec kato-clickhouse clickhouse-client --query "
        SELECT
            database,
            table,
            formatReadableSize(sum(bytes_on_disk)) AS size
        FROM system.parts
        WHERE active = 1
        GROUP BY database, table
        ORDER BY sum(bytes_on_disk) DESC
        LIMIT 5
        FORMAT PrettyCompact
        " 2>/dev/null
        echo ""

        # Redis Memory Usage
        echo -e "${GREEN}Redis Memory Usage:${NC}"

        if docker ps --format '{{.Names}}' | grep -q "^kato-redis$"; then
            # Get Docker memory limit for Redis
            REDIS_DOCKER_LIMIT=$(docker inspect kato-redis --format='{{.HostConfig.Memory}}' 2>/dev/null)
            REDIS_DOCKER_LIMIT_GB=$((REDIS_DOCKER_LIMIT / 1024 / 1024 / 1024))

            if [ "$REDIS_DOCKER_LIMIT" -eq 0 ]; then
                echo "  Docker Memory Limit: Unlimited"
                REDIS_DOCKER_LIMIT_MB=999999  # No limit
            else
                echo "  Docker Memory Limit: ${REDIS_DOCKER_LIMIT_GB}GB"
                REDIS_DOCKER_LIMIT_MB=$((REDIS_DOCKER_LIMIT / 1024 / 1024))
            fi

            # Get Redis memory stats
            REDIS_USED_MEMORY=$(docker exec kato-redis redis-cli INFO memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
            REDIS_MAXMEMORY=$(docker exec kato-redis redis-cli INFO memory 2>/dev/null | grep "maxmemory_human:" | cut -d: -f2 | tr -d '\r')
            REDIS_MEM_FRAG=$(docker exec kato-redis redis-cli INFO memory 2>/dev/null | grep "mem_fragmentation_ratio:" | cut -d: -f2 | tr -d '\r')

            # Get eviction stats
            EVICTED_KEYS=$(docker exec kato-redis redis-cli INFO stats 2>/dev/null | grep "evicted_keys:" | cut -d: -f2 | tr -d '\r')
            KEYSPACE_HITS=$(docker exec kato-redis redis-cli INFO stats 2>/dev/null | grep "keyspace_hits:" | cut -d: -f2 | tr -d '\r')
            KEYSPACE_MISSES=$(docker exec kato-redis redis-cli INFO stats 2>/dev/null | grep "keyspace_misses:" | cut -d: -f2 | tr -d '\r')

            # Get key counts
            REDIS_KEYS=$(docker exec kato-redis redis-cli DBSIZE 2>/dev/null | grep -oE '[0-9]+')

            echo "  Used Memory: $REDIS_USED_MEMORY"
            echo "  Max Memory: $REDIS_MAXMEMORY"
            echo "  Memory Fragmentation: $REDIS_MEM_FRAG"
            echo "  Total Keys: $REDIS_KEYS"
            echo "  Evicted Keys: $EVICTED_KEYS"

            # Calculate hit rate
            if [ -n "$KEYSPACE_HITS" ] && [ -n "$KEYSPACE_MISSES" ]; then
                TOTAL_REQUESTS=$((KEYSPACE_HITS + KEYSPACE_MISSES))
                if [ "$TOTAL_REQUESTS" -gt 0 ]; then
                    HIT_RATE=$((100 * KEYSPACE_HITS / TOTAL_REQUESTS))
                    echo "  Cache Hit Rate: ${HIT_RATE}%"
                fi
            fi

            # Parse used memory into MB for BGSAVE calculations
            REDIS_USED_MB=$(echo "$REDIS_USED_MEMORY" | grep -oE '[0-9.]+' | head -1)
            REDIS_USED_UNIT=$(echo "$REDIS_USED_MEMORY" | grep -oE '[MGK]B?' | head -1)

            case "$REDIS_USED_UNIT" in
                G|GB) REDIS_USED_MB=$(echo "$REDIS_USED_MB * 1024" | bc -l 2>/dev/null || echo "0") ;;
                M|MB) REDIS_USED_MB=$(echo "$REDIS_USED_MB" | bc -l 2>/dev/null || echo "0") ;;
                K|KB) REDIS_USED_MB=$(echo "$REDIS_USED_MB / 1024" | bc -l 2>/dev/null || echo "0") ;;
                *) REDIS_USED_MB="0" ;;
            esac

            # Remove decimal for integer comparison
            REDIS_USED_MB=${REDIS_USED_MB%.*}

            # Calculate BGSAVE fork requirements (2x current usage for worst case COW)
            BGSAVE_REQUIRED_MB=$((REDIS_USED_MB * 2))
            BGSAVE_REQUIRED_GB=$(echo "scale=1; $BGSAVE_REQUIRED_MB / 1024" | bc)

            echo "  BGSAVE Fork Requirement: ~${BGSAVE_REQUIRED_GB}GB (2x current usage)"

            # Calculate total memory needed during BGSAVE
            TOTAL_NEEDED_MB=$((REDIS_USED_MB + BGSAVE_REQUIRED_MB))
            TOTAL_NEEDED_GB=$(echo "scale=1; $TOTAL_NEEDED_MB / 1024" | bc)

            echo "  Total During BGSAVE: ~${TOTAL_NEEDED_GB}GB (parent + fork)"

            # Check for recent SIGKILL events (OOM killer)
            OOM_EVENTS=$(docker logs kato-redis --tail 1000 2>&1 | grep -c "terminated by signal 9")

            if [ "$OOM_EVENTS" -gt 0 ]; then
                echo -e "  ${RED}✗ OOM Events:${NC} $OOM_EVENTS SIGKILL events detected in logs!"
                echo "    Redis is being killed by Docker OOM killer during BGSAVE"
                REDIS_OOM_DETECTED=1
            else
                echo -e "  ${GREEN}✓ OOM Events:${NC} No SIGKILL events detected"
                REDIS_OOM_DETECTED=0
            fi

            # Check if Redis is currently loading
            REDIS_LOADING=$(docker exec kato-redis redis-cli INFO persistence 2>/dev/null | grep "^loading:" | cut -d: -f2 | tr -d '\r')
            if [ "$REDIS_LOADING" = "1" ]; then
                echo -e "  ${YELLOW}⚠ Status:${NC} Currently loading dataset from disk"
                echo "    This indicates a recent restart (possibly from OOM)"
            fi

            # Check if BGSAVE will fit in Docker limit
            REDIS_SAFE_FOR_BGSAVE=1

            if [ "$REDIS_DOCKER_LIMIT" -ne 0 ]; then
                if [ "$TOTAL_NEEDED_MB" -gt "$REDIS_DOCKER_LIMIT_MB" ]; then
                    echo ""
                    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                    echo -e "${RED}⚠ CRITICAL: Redis OOM Risk Detected!${NC}"
                    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                    echo -e "  Current Usage:        ${REDIS_USED_MB}MB"
                    echo -e "  BGSAVE Requirement:   ${BGSAVE_REQUIRED_MB}MB"
                    echo -e "  Total Needed:         ${TOTAL_NEEDED_MB}MB"
                    echo -e "  Docker Limit:         ${REDIS_DOCKER_LIMIT_MB}MB"
                    echo -e "  ${RED}Shortfall:            $((TOTAL_NEEDED_MB - REDIS_DOCKER_LIMIT_MB))MB${NC}"
                    echo ""
                    echo -e "  ${RED}Risk:${NC} BGSAVE will likely trigger OOM killer (SIGKILL)"
                    echo -e "  ${RED}Impact:${NC} Redis will crash and restart, disrupting training"
                    echo ""
                    echo -e "  ${YELLOW}Solution:${NC} Increase Redis Docker memory limit:"
                    echo "    Edit docker-compose.yml:"
                    echo "      redis:"
                    echo "        deploy:"
                    echo "          resources:"
                    echo "            limits:"
                    echo "              memory: 16G    # Increase from ${REDIS_DOCKER_LIMIT_GB}GB"
                    echo ""
                    echo "    Then: docker compose down && docker compose up -d"
                    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                    REDIS_SAFE_FOR_BGSAVE=0
                else
                    # Calculate headroom
                    REDIS_HEADROOM_MB=$((REDIS_DOCKER_LIMIT_MB - TOTAL_NEEDED_MB))
                    REDIS_HEADROOM_GB=$(echo "scale=1; $REDIS_HEADROOM_MB / 1024" | bc)

                    if [ "$REDIS_HEADROOM_MB" -lt 2048 ]; then
                        echo -e "  ${YELLOW}⚠ Warning:${NC} Low headroom for BGSAVE (${REDIS_HEADROOM_GB}GB remaining)"
                        echo "    Consider increasing Docker memory limit to 16GB for safety"
                        REDIS_SAFE_FOR_BGSAVE=0
                    else
                        echo -e "  ${GREEN}✓ BGSAVE Safety:${NC} Sufficient headroom (${REDIS_HEADROOM_GB}GB remaining)"
                    fi
                fi
            fi

            # Warning if evictions are happening
            if [ -n "$EVICTED_KEYS" ] && [ "$EVICTED_KEYS" -gt 0 ]; then
                echo -e "  ${YELLOW}⚠ Warning:${NC} $EVICTED_KEYS keys have been evicted (memory limit reached)"
                echo "    Consider: Increasing Redis memory limit or optimizing data structure"
            fi
        else
            echo "  Redis container is not running"
            REDIS_SAFE_FOR_BGSAVE=0
            REDIS_OOM_DETECTED=0
        fi
        echo ""

        # Training Session Guidance (ENHANCED - includes Redis!)
        echo -e "${GREEN}Training Session Guidance:${NC}"

        # Initialize safety flag
        ALL_SAFE=1

        # Check ClickHouse headroom
        if [ "$HEADROOM_PCT" -gt 50 ]; then
            echo "  ✓ ClickHouse memory headroom is healthy (${HEADROOM_PCT}% available)"
        elif [ "$HEADROOM_PCT" -gt 20 ]; then
            echo "  ⚠ ClickHouse memory headroom is moderate (${HEADROOM_PCT}% available)"
            echo "    Monitor during training, consider clearing system logs if usage increases"
            ALL_SAFE=0
        else
            echo "  ✗ ClickHouse memory headroom is low (${HEADROOM_PCT}% available)"
            echo "    Action: Clear system logs with: ./kato-manager.sh clean-logs"
            ALL_SAFE=0
        fi

        # Check Redis safety
        if [ "$REDIS_SAFE_FOR_BGSAVE" -eq 0 ]; then
            echo "  ✗ Redis memory is UNSAFE for BGSAVE - training will likely fail"
            echo "    Action: Increase Docker memory limit to 16GB (see above)"
            ALL_SAFE=0
        elif [ "$REDIS_OOM_DETECTED" -eq 1 ]; then
            echo "  ⚠ Redis has experienced recent OOM events"
            echo "    Action: Monitor closely, consider increasing memory limit"
            ALL_SAFE=0
        else
            echo "  ✓ Redis memory is safe for BGSAVE operations"
        fi

        echo ""
        if [ "$ALL_SAFE" -eq 1 ]; then
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${GREEN}✓ All systems ready for training${NC}"
            echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        else
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${YELLOW}⚠ Address warnings above before training${NC}"
            echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        fi
        echo ""

        print_info "Run './kato-manager.sh monitor' for continuous updates"
        ;;

    monitor)
        print_info "Starting continuous memory monitoring (Ctrl+C to stop)..."
        print_info "Updates every 5 seconds"
        echo ""

        # Check if ClickHouse is running
        if ! docker ps --format '{{.Names}}' | grep -q "^kato-clickhouse$"; then
            print_error "ClickHouse container is not running"
            exit 1
        fi

        while true; do
            clear
            echo "========================================="
            echo "KATO Memory Monitor - $(date '+%Y-%m-%d %H:%M:%S')"
            echo "========================================="
            echo ""

            # Get memory stats
            MEMORY_STATS=$(docker stats kato-clickhouse --no-stream --format "{{.MemUsage}}")
            CURRENT_RAM=$(echo "$MEMORY_STATS" | awk '{print $1}')
            MAX_RAM=$(echo "$MEMORY_STATS" | awk '{print $3}')

            # Get ClickHouse memory usage
            CH_MEMORY=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(value) FROM system.metrics WHERE metric = 'MemoryTracking'" 2>/dev/null || echo "N/A")

            echo -e "${GREEN}RAM Usage:${NC} $CURRENT_RAM / $MAX_RAM"
            echo -e "${GREEN}ClickHouse Tracked:${NC} $CH_MEMORY"
            echo ""

            # Pattern data
            PATTERN_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'kato' AND table = 'patterns_data' AND active = 1" 2>/dev/null || echo "0 B")
            PATTERN_COUNT=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableQuantity(count(*)) FROM kato.patterns_data" 2>/dev/null || echo "0")
            echo -e "${GREEN}Pattern Data:${NC} $PATTERN_SIZE ($PATTERN_COUNT patterns)"

            # System logs
            SYSTEM_LOG_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'system' AND active = 1" 2>/dev/null || echo "0 B")
            echo -e "${GREEN}System Logs:${NC} $SYSTEM_LOG_SIZE"
            echo ""

            # Active queries
            ACTIVE_QUERIES=$(docker exec kato-clickhouse clickhouse-client --query "SELECT count(*) FROM system.processes" 2>/dev/null || echo "0")
            echo -e "${GREEN}Active Queries:${NC} $ACTIVE_QUERIES"
            echo ""

            # Redis stats
            if docker ps --format '{{.Names}}' | grep -q "^kato-redis$"; then
                REDIS_USED=$(docker exec kato-redis redis-cli INFO memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
                REDIS_MAX=$(docker exec kato-redis redis-cli INFO memory 2>/dev/null | grep "maxmemory_human:" | cut -d: -f2 | tr -d '\r')
                REDIS_KEYS=$(docker exec kato-redis redis-cli DBSIZE 2>/dev/null | grep -oE '[0-9]+')
                EVICTED=$(docker exec kato-redis redis-cli INFO stats 2>/dev/null | grep "evicted_keys:" | cut -d: -f2 | tr -d '\r')

                echo -e "${GREEN}Redis:${NC} $REDIS_USED / $REDIS_MAX ($REDIS_KEYS keys, $EVICTED evicted)"
                echo ""
            fi

            echo "Press Ctrl+C to stop monitoring"
            sleep 5
        done
        ;;

    clean-logs)
        print_warn "⚠️  This will TRUNCATE ClickHouse system logs (query_log, metric_log, etc.)"
        print_warn "Pattern data will NOT be affected."
        echo -e "${YELLOW}Continue? (yes/N)${NC}"
        read -r response
        if [[ "$response" == "yes" ]]; then
            print_info "Truncating ClickHouse system logs..."

            # Truncate system logs
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.query_log" 2>/dev/null
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.text_log" 2>/dev/null
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.trace_log" 2>/dev/null
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.metric_log" 2>/dev/null
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.asynchronous_metric_log" 2>/dev/null
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.part_log" 2>/dev/null
            docker exec kato-clickhouse clickhouse-client --query "TRUNCATE TABLE IF EXISTS system.processors_profile_log" 2>/dev/null

            print_info "✓ System logs truncated"

            # Show new size
            SYSTEM_LOG_SIZE=$(docker exec kato-clickhouse clickhouse-client --query "SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE database = 'system' AND active = 1" 2>/dev/null)
            print_info "Current system log size: $SYSTEM_LOG_SIZE"
        else
            print_info "Operation cancelled"
        fi
        ;;

    help|*)
        echo "KATO Deployment Manager"
        echo ""
        echo "Usage: ./kato-manager.sh [COMMAND] [SERVICE] [OPTIONS]"
        echo ""
        echo "Commands:"
        echo "  start [SERVICE]    - Start service(s) (default: all)"
        echo "  stop [SERVICE]     - Stop service(s) (default: all)"
        echo "  restart [SERVICE]  - Restart service(s) (default: all)"
        echo "  pull               - Pull latest KATO image from registry"
        echo "  update             - Pull latest image and restart KATO"
        echo "  logs [SERVICE] [N] - Show last N lines of logs (default: kato, 50 lines)"
        echo "  follow [SERVICE]   - Follow logs in real-time (default: kato)"
        echo "  status             - Check all service status"
        echo "  verify             - Verify ClickHouse memory configuration for training"
        echo "  memory             - Show detailed memory usage report (RAM + disk)"
        echo "  monitor            - Continuous memory monitoring (updates every 5s)"
        echo "  clean-logs         - Truncate ClickHouse system logs (keeps pattern data)"
        echo "  clean-data         - Delete all data in ClickHouse, Qdrant, and Redis"
        echo "  clean              - Remove all containers and volumes"
        echo "  help               - Show this help message"
        echo ""
        echo "Services: $ALL_SERVICES"
        echo ""
        echo "Examples:"
        echo "  ./kato-manager.sh start              # Start all services (including dashboard)"
        echo "  ./kato-manager.sh start dashboard    # Start dashboard only"
        echo "  ./kato-manager.sh update             # Update KATO to latest version"
        echo "  ./kato-manager.sh status             # Check all services"
        echo "  ./kato-manager.sh verify             # Verify ClickHouse memory config (before training)"
        echo "  ./kato-manager.sh memory             # Check current memory usage (one-time)"
        echo "  ./kato-manager.sh monitor            # Watch memory usage in real-time"
        echo "  ./kato-manager.sh clean-logs         # Clear system logs if memory is low"
        echo "  ./kato-manager.sh logs kato 100      # Show last 100 lines from KATO"
        echo "  ./kato-manager.sh follow dashboard   # Follow dashboard logs in real-time"
        echo "  ./kato-manager.sh restart kato       # Restart only KATO"
        echo "  ./kato-manager.sh stop dashboard     # Stop dashboard (keeps KATO running)"
        echo "  ./kato-manager.sh clean-data         # Clear all database data"
        echo ""
        echo "Memory Management Workflow:"
        echo "  1. Before training: ./kato-manager.sh verify"
        echo "  2. During training: ./kato-manager.sh monitor (in separate terminal)"
        echo "  3. If low memory:   ./kato-manager.sh clean-logs"
        echo ""
        echo "Documentation:"
        echo "  KATO API:  http://localhost:8000/docs (when running)"
        echo "  Dashboard: http://localhost:3001 (when running)"
        ;;
esac
