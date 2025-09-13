#!/bin/bash

# KATO v1 to v2 Migration Helper
# This script helps migrate from v1 to v2 smoothly

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║            KATO v1.0 → v2.0 Migration Helper            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check current status
echo "Checking current KATO deployment..."
echo ""

V1_RUNNING=false
V2_RUNNING=false

if docker ps 2>/dev/null | grep -q "kato-primary[^-]\|kato-testing[^-]\|kato-analytics[^-]"; then
    V1_RUNNING=true
    echo "  📍 KATO v1.0 is currently running"
fi

if docker ps 2>/dev/null | grep -q "kato-primary-v2\|kato-testing-v2\|kato-analytics-v2"; then
    V2_RUNNING=true
    echo "  📍 KATO v2.0 is currently running"
fi

if [ "$V1_RUNNING" = false ] && [ "$V2_RUNNING" = false ]; then
    echo "  📍 No KATO services are currently running"
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Explain v2.0 benefits
echo -e "${GREEN}✨ KATO v2.0 Benefits:${NC}"
echo ""
echo "  ✅ Multi-user session isolation (no data collision)"
echo "  ✅ Database write guarantees (no data loss)"
echo "  ✅ Redis session storage for scalability"
echo "  ✅ Full backward compatibility with v1 API"
echo "  ✅ Production-ready architecture"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Migration options
echo -e "${BLUE}Migration Options:${NC}"
echo ""
echo "1) Quick Migration - Stop v1, Start v2 (Recommended)"
echo "2) Test v2 First - Run v2 alongside v1 (different ports)"
echo "3) Full Clean Migration - Remove everything and start fresh"
echo "4) Just Show Me How - Display manual commands"
echo "5) Cancel"
echo ""

read -p "Select option (1-5): " -n 1 -r
echo ""
echo ""

case $REPLY in
    1)
        echo -e "${YELLOW}Quick Migration Selected${NC}"
        echo ""
        
        if [ "$V1_RUNNING" = true ]; then
            echo "Stopping v1.0 services..."
            KATO_VERSION=v1 ./kato-manager.sh down
            echo "✅ v1.0 stopped"
            echo ""
        fi
        
        if [ "$V2_RUNNING" = true ]; then
            echo "v2.0 is already running!"
        else
            echo "Starting v2.0 services..."
            ./kato-manager.sh build
            ./kato-manager.sh start
            echo ""
        fi
        
        echo "Testing v2.0 deployment..."
        sleep 5
        python3 test_v2_quick.py
        
        echo ""
        echo -e "${GREEN}✅ Migration Complete!${NC}"
        echo ""
        echo "KATO v2.0 is now your default version."
        echo "All future commands will use v2.0 by default."
        echo ""
        echo "Quick Reference:"
        echo "  ./kato-manager.sh start      # Starts v2.0"
        echo "  ./kato-manager.sh status     # Shows v2.0 status"
        echo "  python test_v2_demo.py       # Test v2.0 features"
        ;;
        
    2)
        echo -e "${YELLOW}Test Mode Selected${NC}"
        echo ""
        echo "This will run v2.0 on different ports for testing."
        echo ""
        
        # Create temporary compose file for testing
        cat > docker-compose.v2.test.yml << 'EOF'
version: '3.8'

services:
  kato-test-v2:
    build:
      context: .
      dockerfile: Dockerfile.v2
    image: kato:v2
    container_name: kato-test-v2
    environment:
      - PROCESSOR_ID=test-v2
      - PROCESSOR_NAME=Test-v2
      - MONGO_BASE_URL=mongodb://localhost:27017
      - QDRANT_HOST=localhost
      - QDRANT_PORT=6333
      - REDIS_URL=redis://localhost:6379
      - ENABLE_V2_FEATURES=true
      - LOG_LEVEL=INFO
    network_mode: host
    ports:
      - "8004:8000"
EOF
        
        echo "Building v2.0 test image..."
        docker build -f Dockerfile.v2 -t kato:v2 .
        
        echo "Starting v2.0 test instance on port 8004..."
        docker-compose -f docker-compose.v2.test.yml up -d
        
        echo ""
        echo -e "${GREEN}✅ Test instance started!${NC}"
        echo ""
        echo "v1.0 remains on ports 8001-8003"
        echo "v2.0 test is on port 8004"
        echo ""
        echo "Test v2.0: curl http://localhost:8004/v2/health"
        echo ""
        echo "When ready to switch:"
        echo "  ./kato-manager.sh switch v2"
        ;;
        
    3)
        echo -e "${YELLOW}Full Clean Migration Selected${NC}"
        echo ""
        echo -e "${RED}⚠️  WARNING: This will remove all containers and volumes!${NC}"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo ""
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Removing all KATO containers and volumes..."
            
            # Stop everything
            docker-compose down -v 2>/dev/null || true
            docker-compose -f docker-compose.v2.yml down -v 2>/dev/null || true
            
            # Remove any stray containers
            docker rm -f $(docker ps -a | grep kato | awk '{print $1}') 2>/dev/null || true
            
            echo "✅ Cleanup complete"
            echo ""
            
            echo "Starting fresh v2.0 deployment..."
            ./kato-manager.sh build
            ./kato-manager.sh start
            
            echo ""
            echo -e "${GREEN}✅ Clean migration complete!${NC}"
            echo ""
            echo "KATO v2.0 is running with fresh databases."
        else
            echo "Cancelled."
        fi
        ;;
        
    4)
        echo -e "${BLUE}Manual Migration Commands:${NC}"
        echo ""
        echo "# Stop v1.0 (if running):"
        echo "KATO_VERSION=v1 ./kato-manager.sh down"
        echo ""
        echo "# Build v2.0:"
        echo "./kato-manager.sh build"
        echo ""
        echo "# Start v2.0:"
        echo "./kato-manager.sh start"
        echo ""
        echo "# Test v2.0:"
        echo "python test_v2_quick.py"
        echo ""
        echo "# Check status:"
        echo "./kato-manager.sh status"
        echo ""
        echo "# View logs:"
        echo "./kato-manager.sh logs"
        echo ""
        echo "# Switch back to v1 (if needed):"
        echo "./kato-manager.sh switch v1"
        ;;
        
    5)
        echo "Migration cancelled."
        exit 0
        ;;
        
    *)
        echo "Invalid option. Migration cancelled."
        exit 1
        ;;
esac

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Need help? Check these resources:"
echo "  - V2_STARTUP_GUIDE.md"
echo "  - docs/specifications/v2.0/"
echo "  - Run: ./kato-manager.sh help"
echo ""