#!/bin/bash
# KATO Single Service Manager
# Simple script to manage the unified KATO service

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

# Command to execute
COMMAND=${1:-help}

case "$COMMAND" in
    start)
        print_info "Starting KATO services..."
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
        ;;
        
    stop)
        print_info "Stopping KATO services..."
        docker-compose down
        print_info "Services stopped"
        ;;
        
    restart)
        print_info "Restarting KATO services..."
        docker-compose restart
        print_info "Services restarted"
        ;;
        
    build)
        print_info "Building KATO Docker image..."
        docker-compose build
        print_info "Build complete"
        ;;
        
    logs)
        SERVICE=${2:-kato}
        print_info "Showing logs for $SERVICE..."
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
        echo "Usage: ./start.sh [COMMAND] [OPTIONS]"
        echo ""
        echo "Commands:"
        echo "  start    - Start all KATO services"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        echo "  build    - Build Docker images"
        echo "  logs     - Show logs (optional: service name)"
        echo "  status   - Check service status"
        echo "  clean    - Remove all containers and volumes"
        echo "  help     - Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./start.sh start          # Start all services"
        echo "  ./start.sh logs kato      # Show KATO logs"
        echo "  ./start.sh status         # Check all services"
        ;;
esac