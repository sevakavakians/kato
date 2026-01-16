#!/usr/bin/env bash
#
# KATO Redis Backup Script
#
# Backs up Redis data (RDB + AOF) to prevent data loss of emotives/metadata.
# Emotives and metadata are ONLY stored in Redis and cannot be recovered from ClickHouse.
#
# Usage:
#   ./scripts/backup_redis.sh [backup_directory]
#
# Environment:
#   REDIS_CONTAINER: Redis container name (default: kato-redis)
#   BACKUP_RETENTION_DAYS: How many days to keep backups (default: 30)
#

set -euo pipefail

# Configuration
REDIS_CONTAINER="${REDIS_CONTAINER:-kato-redis}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_DIR="${1:-./backups/redis}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Redis container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
    log_error "Redis container '${REDIS_CONTAINER}' is not running"
    exit 1
fi

log_info "Starting Redis backup for container: ${REDIS_CONTAINER}"

# Create backup directory
mkdir -p "${BACKUP_PATH}"
log_info "Backup directory: ${BACKUP_PATH}"

# Trigger Redis to save RDB snapshot
log_info "Triggering Redis BGSAVE..."
docker exec "${REDIS_CONTAINER}" redis-cli BGSAVE
sleep 2  # Give Redis time to start the background save

# Wait for BGSAVE to complete
log_info "Waiting for BGSAVE to complete..."
while true; do
    STATUS=$(docker exec "${REDIS_CONTAINER}" redis-cli LASTSAVE)
    docker exec "${REDIS_CONTAINER}" redis-cli INFO persistence | grep -q "rdb_bgsave_in_progress:0" && break
    sleep 1
done
log_info "BGSAVE completed"

# Copy RDB file
log_info "Copying RDB snapshot..."
docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${BACKUP_PATH}/dump.rdb" 2>/dev/null || \
docker cp "${REDIS_CONTAINER}:/data/kato_patterns.rdb" "${BACKUP_PATH}/kato_patterns.rdb" || \
log_warn "No RDB file found"

# Copy AOF directory (Redis 7.0+ uses appendonlydir)
log_info "Copying AOF files..."
if docker exec "${REDIS_CONTAINER}" test -d /data/appendonlydir; then
    docker cp "${REDIS_CONTAINER}:/data/appendonlydir" "${BACKUP_PATH}/" || log_warn "Could not copy appendonlydir"
fi

# Copy standalone AOF file (older Redis versions or custom config)
docker cp "${REDIS_CONTAINER}:/data/appendonly.aof" "${BACKUP_PATH}/appendonly.aof" 2>/dev/null || \
docker cp "${REDIS_CONTAINER}:/data/kato_patterns.aof" "${BACKUP_PATH}/kato_patterns.aof" 2>/dev/null || \
log_warn "No AOF file found (this may be normal if using appendonlydir)"

# Get Redis info for backup metadata
docker exec "${REDIS_CONTAINER}" redis-cli INFO > "${BACKUP_PATH}/redis_info.txt"
docker exec "${REDIS_CONTAINER}" redis-cli DBSIZE > "${BACKUP_PATH}/dbsize.txt"

# Create manifest
cat > "${BACKUP_PATH}/manifest.txt" <<EOF
KATO Redis Backup Manifest
==========================
Timestamp: ${TIMESTAMP}
Container: ${REDIS_CONTAINER}
Redis Keys: $(cat "${BACKUP_PATH}/dbsize.txt" || echo "unknown")

Files included:
$(ls -lh "${BACKUP_PATH}" | tail -n +2)

CRITICAL: This backup contains emotives and metadata that cannot be recovered from ClickHouse!
EOF

# Calculate backup size
BACKUP_SIZE=$(du -sh "${BACKUP_PATH}" | cut -f1)
log_info "Backup completed: ${BACKUP_SIZE}"

# Clean up old backups
if [ -d "${BACKUP_DIR}" ]; then
    log_info "Cleaning up backups older than ${BACKUP_RETENTION_DAYS} days..."
    find "${BACKUP_DIR}" -maxdepth 1 -type d -mtime +${BACKUP_RETENTION_DAYS} -exec rm -rf {} \; 2>/dev/null || true
    REMAINING=$(find "${BACKUP_DIR}" -maxdepth 1 -type d | wc -l)
    log_info "Remaining backups: $((REMAINING - 1))"  # Subtract 1 for the backup_dir itself
fi

log_info "========================================="
log_info "Backup Summary:"
log_info "  Location: ${BACKUP_PATH}"
log_info "  Size: ${BACKUP_SIZE}"
log_info "  Files: $(ls "${BACKUP_PATH}" | wc -l)"
log_info "========================================="
log_info "✅ Backup completed successfully"

# Print restoration instructions
cat <<EOF

To restore this backup:
  1. Stop Redis: docker stop ${REDIS_CONTAINER}
  2. Clear data: docker exec ${REDIS_CONTAINER} rm -rf /data/*
  3. Copy backup: docker cp ${BACKUP_PATH}/. ${REDIS_CONTAINER}:/data/
  4. Start Redis: docker start ${REDIS_CONTAINER}

Or use: ./scripts/restore_redis.sh ${TIMESTAMP}
EOF

exit 0
