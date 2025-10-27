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

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Available services
ALL_SERVICES="mongodb redis qdrant kato"

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
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up -d
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
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up -d "$SERVICE"
            print_info "$SERVICE started"
        fi
        ;;

    stop)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Stopping all KATO services..."
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" down
            print_info "All services stopped"
        else
            print_info "Stopping $SERVICE..."
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" stop "$SERVICE"
            print_info "$SERVICE stopped"
        fi
        ;;

    restart)
        validate_service "$SERVICE"
        if [[ "$SERVICE" == "all" ]]; then
            print_info "Restarting all KATO services..."
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" restart
            print_info "All services restarted"
        else
            print_info "Restarting $SERVICE..."
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" restart "$SERVICE"
            print_info "$SERVICE restarted"
        fi
        ;;

    pull)
        print_info "Pulling latest KATO image from registry..."
        docker pull ghcr.io/sevakavakians/kato:latest
        print_info "Image updated. Run './start.sh restart kato' to use the new version"
        ;;

    update)
        print_info "Updating KATO to latest version..."
        docker pull ghcr.io/sevakavakians/kato:latest
        print_info "Restarting KATO service..."
        docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up -d kato
        print_info "✓ KATO updated and restarted"
        ;;

    logs)
        SERVICE=${2:-kato}
        LINES=${3:-50}
        print_info "Showing last $LINES lines of logs for $SERVICE..."
        docker-compose -f "$SCRIPT_DIR/docker-compose.yml" logs --tail="$LINES" "$SERVICE"
        ;;

    follow)
        SERVICE=${2:-kato}
        print_info "Following logs for $SERVICE (Ctrl+C to stop)..."
        docker-compose -f "$SCRIPT_DIR/docker-compose.yml" logs -f "$SERVICE"
        ;;

    status)
        print_info "Checking service status..."
        docker-compose -f "$SCRIPT_DIR/docker-compose.yml" ps

        # Check KATO health
        echo ""
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            print_info "✓ KATO API is responding"
        else
            print_warn "✗ KATO API is not responding"
        fi

        # Check MongoDB
        if docker exec kato-mongodb mongo --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
            print_info "✓ MongoDB is healthy"
        else
            print_warn "✗ MongoDB is not responding"
            print_info "  Check: docker logs kato-mongodb --tail 50"
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
        ;;

    clean-data)
        print_warn "⚠️  This will DELETE ALL DATA in MongoDB, Qdrant, and Redis!"
        print_warn "Services will remain running but all databases will be cleared."
        echo -e "${RED}Are you absolutely sure? (yes/N)${NC}"
        read -r response
        if [[ "$response" == "yes" ]]; then
            print_info "Clearing all database data..."

            # Clear MongoDB - drop all non-system databases
            print_info "Clearing MongoDB databases..."
            docker exec kato-mongodb mongo --eval "
                db.getMongo().getDBNames().forEach(function(dbName) {
                    if (dbName !== 'admin' && dbName !== 'config' && dbName !== 'local') {
                        print('Dropping database: ' + dbName);
                        db.getSiblingDB(dbName).dropDatabase();
                    }
                });
            " || print_error "Failed to clear MongoDB"

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
            docker-compose -f "$SCRIPT_DIR/docker-compose.yml" down -v
            print_info "Cleanup complete"
        else
            print_info "Cleanup cancelled"
        fi
        ;;

    help|*)
        echo "KATO Deployment Manager"
        echo ""
        echo "Usage: ./start.sh [COMMAND] [SERVICE] [OPTIONS]"
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
        echo "  clean-data         - Delete all data in MongoDB, Qdrant, and Redis"
        echo "  clean              - Remove all containers and volumes"
        echo "  help               - Show this help message"
        echo ""
        echo "Services: $ALL_SERVICES"
        echo ""
        echo "Examples:"
        echo "  ./start.sh start              # Start all services"
        echo "  ./start.sh update             # Update KATO to latest version"
        echo "  ./start.sh status             # Check all services"
        echo "  ./start.sh logs kato 100      # Show last 100 lines from KATO"
        echo "  ./start.sh follow kato        # Follow KATO logs in real-time"
        echo "  ./start.sh restart kato       # Restart only KATO"
        echo "  ./start.sh clean-data         # Clear all database data"
        echo ""
        echo "Documentation: http://localhost:8000/docs (when running)"
        ;;
esac
