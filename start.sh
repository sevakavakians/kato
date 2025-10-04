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
        echo "  clean              - Remove all containers and volumes"
        echo "  help               - Show this help message"
        echo ""
        echo "Services: $ALL_SERVICES"
        echo ""
        echo "Examples:"
        echo "  ./start.sh start              # Start all services"
        echo "  ./start.sh start mongodb      # Start only MongoDB"
        echo "  ./start.sh stop kato          # Stop only KATO"
        echo "  ./start.sh restart redis      # Restart only Redis"
        echo "  ./start.sh logs mongodb 100   # Show last 100 lines from MongoDB"
        echo "  ./start.sh follow kato        # Follow KATO logs in real-time"
        echo "  ./start.sh build kato         # Rebuild only KATO image"
        echo "  ./start.sh status             # Check all services"
        ;;
esac