#!/usr/bin/env bash
#
# KATO Redis Restore Script
#
# Restores Redis data from backup to recover lost emotives/metadata.
#
# Usage:
#   ./scripts/restore_redis.sh <backup_timestamp>
#   ./scripts/restore_redis.sh 20260115_120000
#
# Environment:
#   REDIS_CONTAINER: Redis container name (default: kato-redis)
#

set -euo pipefail

# Configuration
REDIS_CONTAINER="${REDIS_CONTAINER:-kato-redis}"
BACKUP_DIR="${2:-./backups/redis}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check arguments
if [ $# -lt 1 ]; then
    log_error "Usage: $0 <backup_timestamp> [backup_directory]"
    echo ""
    echo "Available backups:"
    ls -1 "${BACKUP_DIR}" 2>/dev/null || echo "  No backups found in ${BACKUP_DIR}"
    exit 1
fi

BACKUP_TIMESTAMP="$1"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_TIMESTAMP}"

# Verify backup exists
if [ ! -d "${BACKUP_PATH}" ]; then
    log_error "Backup not found: ${BACKUP_PATH}"
    echo ""
    echo "Available backups:"
    ls -1 "${BACKUP_DIR}" 2>/dev/null || echo "  No backups found"
    exit 1
fi

log_info "Restore Redis from backup: ${BACKUP_TIMESTAMP}"

# Show manifest if exists
if [ -f "${BACKUP_PATH}/manifest.txt" ]; then
    echo ""
    cat "${BACKUP_PATH}/manifest.txt"
    echo ""
fi

# Confirm restore
read -p "This will REPLACE all current Redis data. Continue? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    log_info "Restore cancelled"
    exit 0
fi

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
    log_error "Redis container '${REDIS_CONTAINER}' is not running"
    exit 1
fi

# Get current data size for logging
CURRENT_KEYS=$(docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE 2>/dev/null || echo "unknown")
log_warn "Current Redis keys: ${CURRENT_KEYS}"

# Stop Redis (but keep container running)
log_info "Stopping Redis server..."
docker exec "${REDIS_CONTAINER}" redis-cli SHUTDOWN NOSAVE || log_warn "Redis already stopped"
sleep 2

# Clear existing data
log_info "Clearing existing Redis data..."
docker exec "${REDIS_CONTAINER}" sh -c "rm -rf /data/*" || log_error "Failed to clear data"

# Restore RDB file
log_info "Restoring RDB snapshot..."
if [ -f "${BACKUP_PATH}/dump.rdb" ]; then
    docker cp "${BACKUP_PATH}/dump.rdb" "${REDIS_CONTAINER}:/data/dump.rdb"
elif [ -f "${BACKUP_PATH}/kato_patterns.rdb" ]; then
    docker cp "${BACKUP_PATH}/kato_patterns.rdb" "${REDIS_CONTAINER}:/data/kato_patterns.rdb"
else
    log_warn "No RDB file found in backup"
fi

# Restore AOF directory
log_info "Restoring AOF files..."
if [ -d "${BACKUP_PATH}/appendonlydir" ]; then
    docker cp "${BACKUP_PATH}/appendonlydir" "${REDIS_CONTAINER}:/data/"
fi

# Restore standalone AOF file
if [ -f "${BACKUP_PATH}/appendonly.aof" ]; then
    docker cp "${BACKUP_PATH}/appendonly.aof" "${REDIS_CONTAINER}:/data/appendonly.aof"
elif [ -f "${BACKUP_PATH}/kato_patterns.aof" ]; then
    docker cp "${BACKUP_PATH}/kato_patterns.aof" "${REDIS_CONTAINER}:/data/kato_patterns.aof"
else
    log_warn "No AOF file found in backup"
fi

# Restart Redis container
log_info "Restarting Redis container..."
docker restart "${REDIS_CONTAINER}"

# Wait for Redis to be ready
log_info "Waiting for Redis to start..."
for i in {1..30}; do
    if docker exec "${REDIS_CONTAINER}" redis-cli PING &>/dev/null; then
        break
    fi
    sleep 1
done

# Verify restoration
RESTORED_KEYS=$(docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE 2>/dev/null || echo "0")
log_info "Restored Redis keys: ${RESTORED_KEYS}"

if [ "${RESTORED_KEYS}" -gt 0 ]; then
    log_info "========================================="
    log_info "✅ Restore completed successfully"
    log_info "  Backup: ${BACKUP_TIMESTAMP}"
    log_info "  Keys before: ${CURRENT_KEYS}"
    log_info "  Keys after: ${RESTORED_KEYS}"
    log_info "========================================="
else
    log_error "Restore may have failed - Redis has 0 keys"
    exit 1
fi

exit 0
