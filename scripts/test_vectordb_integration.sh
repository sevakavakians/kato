#!/bin/bash

# Test script for vector database integration with KATO
# This script verifies that the vector database starts automatically with KATO

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
KATO_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Testing Vector Database Integration with KATO${NC}"
echo "=============================================="
echo

# Test 1: Start KATO with vector database (default)
echo -e "${BLUE}Test 1: Starting KATO with vector database (default behavior)${NC}"
"$KATO_ROOT/kato-manager.sh" start

# Wait for services to start
sleep 5

# Check if vector database is running
if docker ps --format '{{.Names}}' | grep -q "qdrant-${USER}-1"; then
    echo -e "${GREEN}✓ Qdrant vector database started automatically${NC}"
else
    echo -e "${RED}✗ Qdrant vector database did not start${NC}"
    exit 1
fi

# Check if Redis cache is running
if docker ps --format '{{.Names}}' | grep -q "redis-cache-${USER}-1"; then
    echo -e "${GREEN}✓ Redis cache started automatically${NC}"
else
    echo -e "${YELLOW}⚠ Redis cache not running (optional)${NC}"
fi

# Check KATO status
"$KATO_ROOT/kato-manager.sh" status

echo
echo -e "${BLUE}Test 2: Stopping all services${NC}"
"$KATO_ROOT/kato-manager.sh" stop --all --with-mongo

sleep 3

echo
echo -e "${BLUE}Test 3: Starting KATO WITHOUT vector database${NC}"
"$KATO_ROOT/kato-manager.sh" start --no-vectordb

# Wait for services to start
sleep 5

# Check that vector database is NOT running
if docker ps --format '{{.Names}}' | grep -q "qdrant-${USER}-1"; then
    echo -e "${RED}✗ Qdrant should not be running with --no-vectordb flag${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Qdrant correctly not started with --no-vectordb${NC}"
fi

# Check KATO is still running
if docker ps --format '{{.Names}}' | grep -q "kato-"; then
    echo -e "${GREEN}✓ KATO running without vector database${NC}"
else
    echo -e "${RED}✗ KATO failed to start without vector database${NC}"
    exit 1
fi

echo
echo -e "${BLUE}Test 4: Testing vector database commands${NC}"

# Stop KATO
"$KATO_ROOT/kato-manager.sh" stop --all --no-mongo

# Test vector database commands
echo "Testing vectordb start command..."
"$KATO_ROOT/kato-manager.sh" vectordb start

sleep 3

echo "Testing vectordb status command..."
"$KATO_ROOT/kato-manager.sh" vectordb status

echo "Testing vectordb stop command..."
"$KATO_ROOT/kato-manager.sh" vectordb stop

echo
echo -e "${GREEN}==============================================
All tests passed successfully!
Vector database integration is working correctly.
==============================================${NC}"

# Cleanup
echo
echo -e "${BLUE}Cleaning up...${NC}"
"$KATO_ROOT/kato-manager.sh" stop --all --with-mongo

echo -e "${GREEN}Test complete!${NC}"