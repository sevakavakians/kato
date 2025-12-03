# GPU Optimization - Quick Start Guide

**For continuing work between sessions**

---

## 🎯 Where We Are

**Status:** Planning Complete, Ready for Implementation
**Date:** 2025-01-20
**Next Phase:** Phase 1 - Foundation & Profiling

---

## 📖 Essential Reading (5 minutes)

**Before starting work, read these in order:**

1. **This file** (you're here!)
2. `docs/gpu/IMPLEMENTATION_PLAN.md` (full plan, 30 min read)
3. `CLAUDE.md` (project context, review pattern terminology)

---

## 🚀 Starting Phase 1

### **Objective**
Establish baseline performance and set up GPU development environment.

### **Immediate Tasks**

```bash
# 1. Create Phase 1 branch
git checkout -b feat/gpu-optimization-phase1

# 2. Create directory structure
mkdir -p kato/gpu
mkdir -p tests/tests/gpu
mkdir -p benchmarks
mkdir -p docs/gpu

# 3. Set up GPU development environment
./scripts/setup_gpu_dev.sh  # Create this script

# 4. Verify GPU access
python -c "import cupy; print(f'GPUs: {cupy.cuda.runtime.getDeviceCount()}')"

# 5. Create baseline benchmark
# Start with: benchmarks/baseline.py
```

### **Phase 1 Deliverables Checklist**

- [ ] GPU development environment operational
- [ ] Baseline performance benchmarks documented
- [ ] Symbol vocabulary encoder implemented (`kato/gpu/encoder.py`)
- [ ] Test data generators created (`tests/tests/gpu/data_generators.py`)
- [ ] Unit tests for encoder passing

---

## 🔑 Key Concepts

### **The Problem**
KATO's pattern matching is sequential:
```python
for pattern in 10_million_patterns:
    similarity = calculate_similarity(pattern, query)
    if similarity >= threshold:
        results.append(pattern)
```
**Time:** ~10+ seconds for 10M patterns

### **The Solution**
GPU parallel processing:
```python
# All patterns processed simultaneously on 10,000 GPU cores
similarities = gpu_kernel(all_patterns, query)  # 50ms
results = filter(similarities >= threshold)
```
**Time:** ~50-100ms for 10M patterns
**Speedup:** 100-200x

### **Key Insight**
- Patterns are **independent** (embarrassingly parallel)
- Each pattern comparison needs **no shared state**
- Perfect for GPU (10,000+ cores)

---

## 📁 File Structure Reference

```
kato/
├── gpu/                      # NEW - GPU optimization module
│   ├── encoder.py           # Symbol → integer encoding
│   ├── matcher.py           # Main GPU matcher class
│   ├── kernels.py           # CUDA kernels
│   ├── memory_manager.py    # GPU memory management
│   └── sync_manager.py      # Sync trigger logic
│
├── searches/
│   └── pattern_search.py    # MODIFY - integrate GPU option
│
└── workers/
    └── pattern_processor.py  # MODIFY - use GPU matcher

tests/tests/gpu/              # NEW - GPU test suite
├── test_encoder.py
├── test_memory_manager.py
├── test_kernels.py
├── test_matcher.py
└── test_sync.py

benchmarks/                   # NEW - Performance testing
├── baseline.py              # Current performance
└── gpu_benchmarks.py        # GPU performance

docs/gpu/                     # THIS DIRECTORY
├── IMPLEMENTATION_PLAN.md   # Full project plan
├── QUICK_START.md          # This file
├── PHASE1_GUIDE.md         # Phase 1 details
└── ARCHITECTURE.md         # System design
```

---

## 🎨 Architecture At A Glance

```
Query Flow:
STM → Encode → GPU Matching (50ms) ┐
                                    ├→ Merge → Filter → Return
      Encode → CPU Matching (5ms)  ┘

Learning Flow:
New Pattern → CPU Tier (0.1ms) → [Sync Trigger?] → GPU Batch Update (125ms/1K)
```

### **Dual-Tier Design**

| Tier | Capacity | Purpose | Speed |
|------|----------|---------|-------|
| GPU  | 10M patterns | Stable patterns | 50ms query |
| CPU  | 10K patterns | Recent patterns | 5ms query |

**Why?**
- GPU is fast but slow to update (125ms per 1K patterns)
- CPU is slow to query but instant to update (0.1ms)
- Hybrid gives best of both worlds

---

## 🔧 Development Workflow

### **Standard Development Cycle**

```bash
# 1. Create feature branch
git checkout -b feat/gpu-encoder

# 2. Implement feature
# e.g., kato/gpu/encoder.py

# 3. Write tests
# e.g., tests/tests/gpu/test_encoder.py

# 4. Run tests
pytest tests/tests/gpu/test_encoder.py -v

# 5. Run benchmarks (if applicable)
python benchmarks/baseline.py

# 6. Commit changes
git add .
git commit -m "feat(gpu): implement symbol vocabulary encoder

- Bidirectional symbol↔int mapping
- Database persistence
- Dynamic vocabulary growth
- Thread-safe operations"

# 7. Push and create PR
git push origin feat/gpu-encoder
```

### **Testing Philosophy**

**Test Pyramid:**
- 60% Unit Tests (fast, isolated)
- 30% Integration Tests (realistic, end-to-end)
- 10% Performance Tests (benchmarks, scaling)

**Critical Tests:**
- **Determinism:** GPU results MUST match Python exactly
- **Performance:** Must meet speedup targets
- **Memory:** Must stay within limits

---

## 📊 Success Metrics

### **Phase 1 Targets**

| Metric | Target |
|--------|--------|
| Baseline documented | Yes |
| GPU environment ready | Yes |
| Encoder implemented | Yes |
| Test coverage | >90% |

### **Overall Project Targets**

| Metric | Current | Target | Speedup |
|--------|---------|--------|---------|
| 10M patterns query | 10,000ms | 100ms | 100x |
| 1M patterns query | 1,000ms | 20ms | 50x |
| 100K patterns query | 100ms | 5ms | 20x |
| Learn new pattern | 0.1ms | 0.1ms | 1x (no change) |

---

## 🐛 Common Issues & Solutions

### **Issue: CUDA not found**
```bash
# Verify CUDA installation
nvcc --version

# If not installed:
# - Download CUDA Toolkit 12.x from NVIDIA
# - Install and set PATH
```

### **Issue: CuPy installation fails**
```bash
# Install correct version for your CUDA
pip install cupy-cuda12x  # for CUDA 12.x
# or
pip install cupy-cuda11x  # for CUDA 11.x
```

### **Issue: GPU not accessible in Docker**
```bash
# Verify nvidia-docker installed
nvidia-docker --version

# Use correct compose file
docker compose -f docker compose.gpu.yml up
```

### **Issue: Tests failing - GPU vs Python results differ**
```python
# Add tolerance for floating point comparisons
assert abs(gpu_result - python_result) < 1e-6

# Or use numpy testing
np.testing.assert_allclose(gpu_result, python_result, rtol=1e-6)
```

---

## 🎓 Learning Resources

### **CUDA Programming**
- [CUDA C Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [CuPy Tutorial](https://docs.cupy.dev/en/stable/user_guide/basic.html)
- [GPU Gem: Parallel Algorithm Patterns](https://developer.nvidia.com/gpugems/gpugems3/part-vi-gpu-computing/chapter-39-parallel-prefix-sum-scan-cuda)

### **Pattern Matching Algorithms**
- [Longest Common Subsequence](https://en.wikipedia.org/wiki/Longest_common_subsequence_problem)
- [Python difflib source](https://github.com/python/cpython/blob/main/Lib/difflib.py) (what we're matching)
- [Sequence Alignment](https://en.wikipedia.org/wiki/Sequence_alignment)

### **KATO Internals**
- `kato/searches/pattern_search.py:158-1028` - Current matching implementation
- `kato/workers/pattern_processor.py:362-580` - How predictions are generated
- `kato/representations/prediction.py` - Prediction object structure

---

## 🆘 When Stuck

**Debugging Checklist:**
1. Check logs: `docker logs kato --tail 100`
2. Run single test: `pytest tests/tests/gpu/test_encoder.py::test_encode_symbol -vv`
3. Profile code: `python -m cProfile -o profile.prof script.py`
4. Check GPU: `nvidia-smi` (memory, utilization)
5. Review architecture: `docs/gpu/ARCHITECTURE.md`

**Where to Look:**
- Implementation details: `docs/gpu/IMPLEMENTATION_PLAN.md`
- API changes: `docs/gpu/API.md` (to be created)
- Code examples: `tests/tests/gpu/` directory

---

## 📞 Next Session Handoff

**When ending a session, update this section:**

### **Last Session Summary**
**Date:** [YYYY-MM-DD]
**Work Completed:**
- [List what was done]

**Current Status:**
- [What phase/task you're on]

**Blockers:**
- [Any issues preventing progress]

**Next Steps:**
- [What to do next session]

---

## ✅ Quick Reference Commands

```bash
# Start services
./start.sh

# Run all tests
./run_tests.sh --no-start --no-stop

# Run GPU tests only
pytest tests/tests/gpu/ -v

# Run benchmarks
python benchmarks/baseline.py

# Check GPU status
nvidia-smi

# Monitor GPU usage
watch -n 1 nvidia-smi

# Profile Python code
python -m cProfile -o profile.prof script.py
python -m pstats profile.prof

# Check memory usage
import cupy as cp
print(f"GPU Memory: {cp.get_default_memory_pool().used_bytes() / 1e9:.2f} GB")
```

---

## 🎯 Remember

**Key Principles:**
1. **Determinism First** - GPU must match Python exactly
2. **Performance Second** - Speedup targets are aggressive but achievable
3. **Backward Compatibility** - Opt-in feature, no breaking changes
4. **Test Everything** - Especially determinism and edge cases
5. **Document As You Go** - Update docs with learnings

**You Got This! 🚀**

The hardest part is done (planning). Now it's just implementation.
Each phase builds on the previous one. Take it step by step.

---

**Next:** Read `docs/gpu/PHASE1_GUIDE.md` for detailed Phase 1 instructions
