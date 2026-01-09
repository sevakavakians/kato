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
        echo "  ./kato-manager.sh logs kato 100      # Show last 100 lines from KATO"
        echo "  ./kato-manager.sh follow dashboard   # Follow dashboard logs in real-time"
        echo "  ./kato-manager.sh restart kato       # Restart only KATO"
        echo "  ./kato-manager.sh stop dashboard     # Stop dashboard (keeps KATO running)"
        echo "  ./kato-manager.sh clean-data         # Clear all database data"
        echo ""
        echo "Documentation:"
        echo "  KATO API:  http://localhost:8000/docs (when running)"
        echo "  Dashboard: http://localhost:3001 (when running)"
        ;;
esac
