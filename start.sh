#!/bin/bash
# KATO Service Manager
# Manage KATO services individually or all together

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

# Available services
ALL_SERVICES="redis qdrant clickhouse kato"

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
            docker-compose up -d
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
            docker-compose up -d "$SERVICE"
            print_info "$SERVICE started"
        fi
        ;;

    stop)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Stopping all KATO services..."
            docker-compose down
            print_info "All services stopped"
        else
            print_info "Stopping $SERVICE..."
            docker-compose stop "$SERVICE"
            print_info "$SERVICE stopped"
        fi
        ;;

    restart)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Restarting all KATO services..."
            docker-compose restart
            print_info "All services restarted"
        else
            print_info "Restarting $SERVICE..."
            docker-compose restart "$SERVICE"
            print_info "$SERVICE restarted"
        fi
        ;;

    build)
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Building all Docker images..."
            docker-compose build
        else
            print_info "Building $SERVICE image..."
            docker-compose build "$SERVICE"
        fi
        print_info "Build complete"
        ;;

    logs)
        SERVICE=${2:-kato}
        LINES=${3:-50}
        print_info "Showing last $LINES lines of logs for $SERVICE..."
        docker-compose logs --tail="$LINES" "$SERVICE"
        ;;

    follow)
        SERVICE=${2:-kato}
        print_info "Following logs for $SERVICE (Ctrl+C to stop)..."
        docker-compose logs -f "$SERVICE"
        ;;

    status)
        print_info "Checking service status..."
        docker-compose ps

        # Check KATO health
        echo ""
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            print_info "✓ KATO API is responding"
        else
            print_warn "✗ KATO API is not responding"
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

        # Check ClickHouse
        if curl -s http://localhost:8123/ping > /dev/null 2>&1; then
            print_info "✓ ClickHouse is healthy"
        else
            print_warn "✗ ClickHouse is not responding"
            print_warn "  ClickHouse is REQUIRED for pattern storage"
        fi
        ;;

    clean-data)
        print_warn "⚠️  This will DELETE ALL DATA in Qdrant, Redis, and ClickHouse!"
        print_warn "Services will remain running but all databases will be cleared."
        echo -e "${RED}Are you absolutely sure? (yes/N)${NC}"
        read -r response
        if [[ "$response" == "yes" ]]; then
            print_info "Clearing all database data..."

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

            # Clear ClickHouse - drop patterns_data table
            print_info "Clearing ClickHouse data..."
            docker exec kato-clickhouse clickhouse-client --query "DROP TABLE IF EXISTS default.patterns_data" 2>/dev/null || print_warn "ClickHouse not available or already empty"
            # Recreate table from init script
            docker exec kato-clickhouse clickhouse-client --queries-file /docker-entrypoint-initdb.d/init.sql 2>/dev/null || print_warn "Could not recreate ClickHouse table"

            print_info "✓ All database data has been cleared!"
            print_warn "Services are still running. Use './start.sh restart' if needed."
        else
            print_info "Data cleanup cancelled"
        fi
        ;;

    clean)
        print_warn "This will remove all containers and volumes. Are you sure? (y/N)"
        read -r response
        if [[ "$response" == "y" || "$response" == "Y" ]]; then
            print_info "Cleaning up KATO services..."
            docker-compose down -v
            print_info "Cleanup complete"
        else
            print_info "Cleanup cancelled"
        fi
        ;;

    mode)
        print_info "KATO Architecture Mode: Hybrid (ClickHouse + Redis)"
        echo ""
        print_info "ℹ️  MongoDB has been removed from KATO."
        print_info "   Hybrid architecture (ClickHouse + Redis) is now the only mode."
        echo ""
        print_info "Requirements:"
        print_info "  • ClickHouse service running"
        print_info "  • Redis service running"
        print_info "  • Qdrant service running (for vector embeddings)"
        echo ""
        print_info "Check service status:"
        print_info "  ./start.sh status"
        ;;

    clean-all)
        print_error "⚠️  NUCLEAR OPTION: This will COMPLETELY RESET KATO!"
        print_warn "This will:"
        print_warn "  1. Stop all services"
        print_warn "  2. Remove all containers"
        print_warn "  3. Delete all volumes (qdrant-data, redis-data, clickhouse-data, clickhouse-logs)"
        print_warn "  4. Restart services from clean state"
        echo -e "${RED}Type 'DELETE EVERYTHING' to confirm:${NC}"
        read -r response
        if [[ "$response" == "DELETE EVERYTHING" ]]; then
            print_info "Stopping all services..."
            docker-compose down

            print_info "Removing all volumes..."
            docker volume rm kato_qdrant-data kato_redis-data kato_clickhouse-data kato_clickhouse-logs 2>/dev/null || print_warn "Some volumes may not exist"

            print_info "Starting fresh services..."
            docker-compose up -d

            print_info "Waiting for services to be ready..."
            sleep 5

            # Check health
            if curl -s http://localhost:8000/health > /dev/null; then
                print_info "✓ KATO has been completely reset and is now running clean"
                print_info "Access KATO at: http://localhost:8000"
            else
                print_warn "Services may still be starting up..."
            fi
        else
            print_info "Complete reset cancelled"
        fi
        ;;

    help|*)
        echo "KATO Service Manager"
        echo ""
        echo "Usage: ./start.sh [COMMAND] [SERVICE] [OPTIONS]"
        echo ""
        echo "Commands:"
        echo "  start [SERVICE]    - Start service(s) (default: all)"
        echo "  stop [SERVICE]     - Stop service(s) (default: all)"
        echo "  restart [SERVICE]  - Restart service(s) (default: all)"
        echo "  build [SERVICE]    - Build Docker image(s) (default: all)"
        echo "  logs [SERVICE] [N] - Show last N lines of logs (default: kato, 50 lines)"
        echo "  follow [SERVICE]   - Follow logs in real-time (default: kato)"
        echo "  status             - Check all service status"
        echo "  mode               - Show architecture mode info"
        echo "  clean-data         - Delete all data in Qdrant, Redis, and ClickHouse"
        echo "  clean              - Remove all containers and volumes"
        echo "  clean-all          - NUCLEAR: Complete reset - stops services, removes volumes, restarts clean"
        echo "  help               - Show this help message"
        echo ""
        echo "Services: $ALL_SERVICES"
        echo ""
        echo "Examples:"
        echo "  ./start.sh start              # Start all services"
        echo "  ./start.sh start redis        # Start only Redis"
        echo "  ./start.sh stop kato          # Stop only KATO"
        echo "  ./start.sh restart clickhouse # Restart only ClickHouse"
        echo "  ./start.sh logs kato 100      # Show last 100 lines from KATO"
        echo "  ./start.sh follow kato        # Follow KATO logs in real-time"
        echo "  ./start.sh build kato         # Rebuild only KATO image"
        echo "  ./start.sh status             # Check all services"
        echo "  ./start.sh mode               # Show architecture mode info"
        echo "  ./start.sh clean-data         # Clear all database data (soft reset)"
        echo "  ./start.sh clean-all          # Complete reset with volume removal (hard reset)"
        echo ""
        echo "Architecture Notes:"
        echo "  • KATO uses ClickHouse + Redis hybrid architecture (MongoDB removed)"
        echo "  • Requires ClickHouse, Redis, and Qdrant services"
        echo "  • 100-300x performance vs legacy MongoDB mode"
        echo "  • See docs/HYBRID_ARCHITECTURE.md for setup guide"
        ;;
esac