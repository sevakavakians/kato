#!/bin/bash

# KATO v2.0 Startup Script
# This script helps manage the transition between v1 and v2 deployments

set -e

echo "╔══════════════════════════════════════════╗"
echo "║        KATO v2.0 Startup Script          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Function to check if v1 is running
check_v1_running() {
    if docker ps | grep -q "kato-primary\|kato-testing\|kato-analytics"; then
        return 0
    else
        return 1
    fi
}

# Function to check if v2 is running
check_v2_running() {
    if docker ps | grep -q "kato-primary-v2\|kato-testing-v2\|kato-analytics-v2"; then
        return 0
    else
        return 1
    fi
}

# Check current status
echo "Checking current deployment status..."
echo ""

if check_v1_running; then
    echo "⚠️  KATO v1.0 services are currently running"
    echo ""
    read -p "Do you want to stop v1.0 and start v2.0? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled. v1.0 services remain running."
        exit 0
    fi
    
    echo "Stopping v1.0 services..."
    docker-compose down
    echo "✅ v1.0 services stopped"
    echo ""
fi

if check_v2_running; then
    echo "ℹ️  KATO v2.0 services are already running"
    echo ""
    read -p "Do you want to restart v2.0 services? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "v2.0 services remain running."
        echo ""
        echo "Access points:"
        echo "  - Primary:   http://localhost:8001"
        echo "  - Testing:   http://localhost:8002"
        echo "  - Analytics: http://localhost:8003"
        echo "  - API Docs:  http://localhost:8001/docs"
        echo ""
        echo "v2.0 Endpoints:"
        echo "  - Session Management: http://localhost:8001/v2/sessions"
        echo "  - Health Check:       http://localhost:8001/v2/health"
        echo ""
        exit 0
    fi
    
    echo "Stopping v2.0 services..."
    docker-compose -f docker-compose.v2.yml down
    echo "✅ v2.0 services stopped"
    echo ""
fi

# Build and start v2.0
echo "Building KATO v2.0 Docker image..."
docker-compose -f docker-compose.v2.yml build

echo ""
echo "Starting KATO v2.0 services..."
docker-compose -f docker-compose.v2.yml up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 5

# Check health of services
echo ""
echo "Checking service health..."

check_health() {
    local service=$1
    local port=$2
    local name=$3
    
    if curl -s -f "http://localhost:${port}/v2/health" > /dev/null 2>&1; then
        echo "  ✅ ${name} (port ${port}): Healthy"
        return 0
    else
        echo "  ⚠️  ${name} (port ${port}): Not responding yet"
        return 1
    fi
}

# Wait for all services with retry
MAX_RETRIES=30
RETRY_COUNT=0
ALL_HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo ""
    
    PRIMARY_OK=false
    TESTING_OK=false
    ANALYTICS_OK=false
    
    check_health "kato-primary-v2" "8001" "Primary" && PRIMARY_OK=true
    check_health "kato-testing-v2" "8002" "Testing" && TESTING_OK=true
    check_health "kato-analytics-v2" "8003" "Analytics" && ANALYTICS_OK=true
    
    if [ "$PRIMARY_OK" = true ] && [ "$TESTING_OK" = true ] && [ "$ANALYTICS_OK" = true ]; then
        ALL_HEALTHY=true
        break
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo ""
        echo "Waiting for services to start... (attempt $RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    fi
done

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║            Startup Complete              ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if [ "$ALL_HEALTHY" = true ]; then
    echo "✅ All KATO v2.0 services are running and healthy!"
else
    echo "⚠️  Some services may not be fully ready yet."
    echo "   Check logs with: docker-compose -f docker-compose.v2.yml logs"
fi

echo ""
echo "📍 Access Points:"
echo "  - Primary:   http://localhost:8001"
echo "  - Testing:   http://localhost:8002"
echo "  - Analytics: http://localhost:8003"
echo "  - MongoDB:   mongodb://localhost:27017"
echo "  - Qdrant:    http://localhost:6333"
echo "  - Redis:     redis://localhost:6379"
echo ""
echo "📚 API Documentation:"
echo "  - v1 API: http://localhost:8001/docs"
echo "  - v2 API: http://localhost:8001/docs#/v2"
echo ""
echo "🔧 v2.0 New Features:"
echo "  - Session Management: POST /v2/sessions"
echo "  - Isolated STMs:     POST /v2/sessions/{id}/observe"
echo "  - Health Check:      GET /v2/health"
echo ""
echo "🧪 Test the implementation:"
echo "  python test_v2_demo.py"
echo ""
echo "📊 View logs:"
echo "  docker-compose -f docker-compose.v2.yml logs -f"
echo ""
echo "🛑 Stop services:"
echo "  docker-compose -f docker-compose.v2.yml down"
echo ""