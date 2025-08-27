# Vector Architecture Migration Guide

## For Existing KATO Users

This guide helps existing KATO users migrate to the new high-performance vector architecture.

## What's Changed?

### Before (Legacy Architecture)
- Vectors stored in MongoDB alongside other data
- Linear O(n) search through all vectors
- Multiprocessing-based parallel search
- 50-500ms typical search time
- Limited to ~10,000 vectors effectively

### After (New Architecture)  
- Vectors stored in dedicated Qdrant database
- HNSW index with O(log n) search
- Async operations with caching
- 5-6ms typical search time
- Scales to millions of vectors
- **10-100x performance improvement**

## Migration Steps

### Step 1: Backup Your Data
```bash
# Backup MongoDB (recommended before any migration)
mongodump --host localhost:27017 --db kato --out ./backup/$(date +%Y%m%d)
```

### Step 2: Update Dependencies
```bash
# Update requirements
pip install qdrant-client>=1.7.0 redis>=4.5.0 aiofiles>=23.0.0

# Or update requirements.txt and reinstall
pip install -r requirements.txt
```

### Step 3: Pull Latest Code
```bash
git pull origin main
```

### Step 4: Rebuild Docker Image
```bash
./kato-manager.sh build
```

### Step 5: Start with Vector Database
```bash
# Stop existing KATO
./kato-manager.sh stop

# Start with vector database (automatic)
./kato-manager.sh start
```

The vector database (Qdrant) will start automatically on port 6333.

### Step 6: Migrate Existing Vectors (Optional)
If you have existing vectors in MongoDB that you want to migrate:

```bash
python scripts/migrate_vectors.py
```

This script will:
1. Connect to MongoDB
2. Extract all vectors
3. Index them in Qdrant
4. Verify migration success

### Step 7: Verify Migration
```bash
# Test basic functionality
python tests/test_vector_simplified.py

# Run comprehensive tests
python tests/test_vector_e2e.py

# Stress test (optional)
python tests/test_vector_stress.py
```

## Code Changes Required

### Minimal Changes (Compatibility Mode)
**No immediate code changes required!** The system maintains backward compatibility:

```python
# Old code still works
from kato.searches.vector_searches import CVCSearcher
searcher = CVCSearcher(num_procs, vectors_kb)
```

### Recommended Changes (For Best Performance)
```python
# New recommended approach
from kato.searches.vector_search_engine import CVCSearcherModern
searcher = CVCSearcherModern(num_procs, vectors_kb)
```

## Configuration Options

### Environment Variables
```bash
# Choose vector backend (default: qdrant)
export VECTORDB_BACKEND=qdrant

# Qdrant connection
export QDRANT_URL=http://localhost:6333

# Vector dimensions (auto-detected if not set)
export VECTOR_DIM=512

# Enable/disable caching
export VECTOR_CACHE_ENABLED=true
export VECTOR_CACHE_SIZE=1000
```

### Docker Compose Configuration
Edit `docker-compose.vectordb.yml` to customize:
- Qdrant ports
- Storage paths
- Memory limits
- Performance settings

## Rollback Plan

If you encounter issues and need to rollback:

### Option 1: Temporary Fallback to MongoDB
```bash
# Set environment variable
export VECTORDB_BACKEND=mongodb

# Restart KATO
./kato-manager.sh restart
```

### Option 2: Full Rollback
```bash
# Stop KATO
./kato-manager.sh stop

# Checkout previous version
git checkout <previous-commit-hash>

# Rebuild without vector database
./kato-manager.sh build

# Start without vector database
./kato-manager.sh start --no-vectordb
```

### Option 3: Restore MongoDB Backup
```bash
# Restore from backup
mongorestore --host localhost:27017 --db kato ./backup/20240827/kato
```

## Performance Comparison

### Benchmark Results
| Metric | Old System | New System | Improvement |
|--------|------------|------------|-------------|
| Search Time (50 vectors) | ~100ms | ~5ms | 20x |
| Search Time (500 vectors) | ~500ms | ~6ms | 83x |
| Learning Time (100 vectors) | ~1000ms | ~160ms | 6x |
| Max Practical Vectors | ~10,000 | 1,000,000+ | 100x |
| Memory Usage | O(n) | O(log n) | Logarithmic |

## Troubleshooting

### Issue: Qdrant fails to start
```bash
# Check if port 6333 is in use
lsof -i :6333

# Use different port
export QDRANT_REST_PORT=6335
./kato-manager.sh restart
```

### Issue: Import errors with numpy
```bash
# Reinstall numpy
pip uninstall numpy
pip install numpy==2.0.2
```

### Issue: Vector search returns no results
```bash
# Check Qdrant is running
curl http://localhost:6333/health

# Verify collection exists
curl http://localhost:6333/collections
```

### Issue: Performance not improved
1. Verify Qdrant is being used:
   ```bash
   docker logs qdrant-$USER-1 | tail -20
   ```
2. Check cache is enabled:
   ```bash
   echo $VECTOR_CACHE_ENABLED
   ```
3. Monitor Qdrant metrics:
   ```bash
   curl http://localhost:6333/metrics
   ```

## FAQ

### Q: Will my existing models still work?
**A:** Yes! All existing models remain compatible. The vector storage backend change is transparent to the model structure.

### Q: Do I need to retrain my models?
**A:** No. Models don't need retraining. However, you may want to rebuild indexes for optimal performance.

### Q: Can I run without Qdrant?
**A:** Yes, but not recommended. Use `./kato-manager.sh start --no-vectordb` to run with MongoDB vectors (legacy mode).

### Q: What about GPU acceleration?
**A:** GPU support is available but not enabled by default. See `docker-compose.vectordb.yml` for GPU configuration.

### Q: How much disk space does Qdrant need?
**A:** Typically 2-3x the size of your vector data. For 1M 512-dim vectors, expect ~2-3GB.

## Support

For issues or questions:
1. Check [Known Issues](./KNOWN_ISSUES_AND_BUGS.md)
2. Review [Breaking Changes](./BREAKING_CHANGES_VECTOR_ARCHITECTURE.md)
3. See [Vector Architecture Documentation](./VECTOR_ARCHITECTURE_IMPLEMENTATION.md)

## Next Steps

After successful migration:
1. Monitor performance improvements
2. Consider enabling GPU acceleration if available
3. Explore advanced Qdrant features (quantization, distributed mode)
4. Remove legacy code with `scripts/remove_old_vector_architecture.sh` (after thorough testing)