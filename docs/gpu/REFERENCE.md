# GPU Optimization Quick Reference

**One-page reference for GPU implementation**

---

## 📊 Performance Targets

| Patterns | Current | Target | Speedup |
|----------|---------|--------|---------|
| 1M | 10,000ms | 100ms | 100x |
| 100K | 1,000ms | 10ms | 100x |
| 10K | 100ms | 2ms | 50x |

---

## 🏗️ Architecture

```
Query: STM → Encode → GPU (50ms) + CPU (5ms) → Merge → Return
Learn: Pattern → CPU tier → [Sync?] → GPU batch
```

**Dual-Tier:**
- GPU: 10M patterns, 50ms query, slow update (125ms/1K)
- CPU: 10K patterns, 5ms query, fast update (0.1ms)

---

## 📁 Key Files

```
kato/gpu/
├── encoder.py          # Symbol ↔ integer
├── matcher.py          # Main GPU matcher
├── kernels.py          # CUDA kernels
├── memory_manager.py   # GPU VRAM
└── sync_manager.py     # Sync triggers

tests/tests/gpu/
└── test_*.py           # Test each component
```

---

## 🔧 Commands

```bash
# Setup
./scripts/setup_gpu_dev.sh
source venv-gpu/bin/activate

# Verify GPU
nvidia-smi
python -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"

# Benchmark
python benchmarks/baseline.py

# Test
pytest tests/tests/gpu/ -v

# Monitor
watch -n 1 nvidia-smi
```

---

## 💻 Code Snippets

### **Encoder Usage**
```python
from kato.gpu.encoder import SymbolVocabularyEncoder

encoder = SymbolVocabularyEncoder(mongodb.metadata)

# Encode
encoded = encoder.encode_sequence(['hello', 'world'])
# Returns: np.array([123, 456], dtype=int32)

# Decode
decoded = encoder.decode_sequence(encoded)
# Returns: ['hello', 'world']
```

### **GPU Memory**
```python
from kato.gpu.memory_manager import GPUMemoryManager

memory = GPUMemoryManager(
    initial_capacity=10_000_000,
    max_pattern_length=100
)

# Add pattern
memory.add_pattern("PTRN|abc", encoded_sequence)

# Get active patterns
patterns, lengths = memory.get_active_patterns()
```

### **CUDA Kernel Launch**
```python
from kato.gpu.kernels import GPUKernels

similarities = GPUKernels.compute_similarities(
    gpu_patterns=patterns,
    gpu_pattern_lengths=lengths,
    gpu_query=query,
    num_patterns=10_000_000,
    max_pattern_length=100
)
# Returns: CuPy array of similarity scores
```

---

## 🧪 Testing Pattern

```python
import pytest
from kato.gpu.encoder import SymbolVocabularyEncoder

@pytest.fixture
def encoder(mongodb):
    return SymbolVocabularyEncoder(mongodb.metadata)

def test_encode_decode(encoder):
    original = ["a", "b", "c"]
    encoded = encoder.encode_sequence(original)
    decoded = encoder.decode_sequence(encoded)
    assert decoded == original
```

---

## 📊 Monitoring

**Metrics to Track:**
```python
# Prometheus
kato_gpu_query_duration_seconds  # Histogram
kato_gpu_memory_bytes            # Gauge
kato_gpu_pattern_count           # Gauge
kato_cpu_pattern_count           # Gauge
```

**Alerts:**
- GPU memory > 90%: Critical
- Query latency p95 > 500ms: Warning
- Sync failures: Critical

---

## 🐛 Debugging

**GPU Not Found:**
```bash
nvcc --version  # Check CUDA
nvidia-smi      # Check drivers
```

**CuPy Import Error:**
```bash
pip install cupy-cuda12x  # Match CUDA version
```

**Results Differ:**
```python
# Use tolerance
np.testing.assert_allclose(gpu, cpu, rtol=1e-6)
```

**Memory Error:**
```python
# Check usage
pool = cp.get_default_memory_pool()
print(f"Used: {pool.used_bytes() / 1e9:.2f} GB")
pool.free_all_blocks()  # Free memory
```

---

## 🔄 Git Workflow

```bash
# Feature branch
git checkout -b feat/gpu-encoder

# Commit
git add .
git commit -m "feat(gpu): implement encoder"

# Push
git push origin feat/gpu-encoder

# PR
gh pr create --title "GPU Encoder" --body "..."
```

---

## 📋 Phase Checklist

**Phase 1:**
- [ ] GPU environment setup
- [ ] Baseline benchmarks
- [ ] Encoder implemented
- [ ] Tests passing

**Phase 2:**
- [ ] RapidFuzz integration
- [ ] CPU optimization
- [ ] 5-10x speedup

**Phase 3:**
- [ ] GPU memory manager
- [ ] CUDA kernels
- [ ] HybridGPUMatcher
- [ ] 50-100x speedup

**Phase 4:**
- [ ] Sync triggers
- [ ] Training mode
- [ ] API endpoints

**Phase 5:**
- [ ] Error handling
- [ ] Monitoring
- [ ] Documentation
- [ ] Production ready

---

## 🎯 Success Criteria

**Critical:**
- ✅ GPU results == Python results (determinism)
- ✅ 100x speedup for 1M patterns
- ✅ Learning latency unchanged (<0.2ms)
- ✅ Memory < 5GB for 10M patterns

**Important:**
- ✅ All tests pass
- ✅ No regressions
- ✅ Documentation complete
- ✅ Production stable

---

## 📚 Documentation

**Full Details:**
- `IMPLEMENTATION_PLAN.md` - Complete plan
- `QUICK_START.md` - Getting started
- `PHASE1_GUIDE.md` - Phase 1 details
- `ARCHITECTURE.md` - System design (TBD)

**KATO Code:**
- `kato/searches/pattern_search.py:158-1028` - Current matcher
- `kato/workers/pattern_processor.py:362-580` - Prediction flow
- `CLAUDE.md` - Project overview

---

## 🆘 Emergency Rollback

```bash
# Disable GPU
export GPU_ENABLED=false

# Or via API
curl -X PUT localhost:8000/gpu/config \
  -d '{"enabled": false}'

# Restart services
docker-compose restart
```

---

## 💡 Key Principles

1. **Determinism First** - GPU must match Python
2. **Test Everything** - Especially edge cases
3. **Document As You Go** - Future you will thank you
4. **Measure Twice, Cut Once** - Benchmark before optimizing

---

## 📞 Resources

**CUDA:**
- [Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [CuPy Docs](https://docs.cupy.dev/)
- [Best Practices](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/)

**Algorithms:**
- [LCS Wikipedia](https://en.wikipedia.org/wiki/Longest_common_subsequence_problem)
- [difflib source](https://github.com/python/cpython/blob/main/Lib/difflib.py)

---

**This reference card contains the most frequently needed information. For details, see full documentation.**
