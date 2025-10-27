# Phase 1: Foundation & Profiling

**Duration:** Week 1-2
**Status:** Not Started
**Prerequisites:** CUDA Toolkit 12.x, CuPy, MongoDB access

---

## 🎯 Phase Objectives

1. **Establish Performance Baseline** - Measure current pattern matching performance
2. **Set Up GPU Environment** - Configure development environment with CUDA/CuPy
3. **Implement Symbol Encoder** - Convert strings to integers for GPU processing
4. **Create Test Infrastructure** - Build comprehensive test suite

---

## 📋 Task Breakdown

### **Task 1.1: Environment Setup** (Day 1)

**Goal:** Get GPU development environment working

#### **Subtasks:**

**1.1.1 Verify CUDA Installation**
```bash
# Check CUDA version
nvcc --version
# Expected: CUDA 12.x

# Check GPU availability
nvidia-smi
# Should show GPU(s)
```

**1.1.2 Install Python Dependencies**
```bash
# Create GPU virtual environment
python3 -m venv venv-gpu
source venv-gpu/bin/activate

# Install CuPy (CUDA 12.x)
pip install cupy-cuda12x

# Install KATO dependencies
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Verify CuPy works
python -c "import cupy as cp; print(f'CuPy version: {cp.__version__}')"
python -c "import cupy as cp; print(f'GPU count: {cp.cuda.runtime.getDeviceCount()}')"
```

**1.1.3 Create GPU Development Script**

Create `scripts/setup_gpu_dev.sh`:
```bash
#!/bin/bash
set -e

echo "Setting up GPU development environment..."

# Check CUDA
if ! command -v nvcc &> /dev/null; then
    echo "ERROR: CUDA Toolkit not found. Install CUDA 12.x"
    exit 1
fi

# Check GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo "ERROR: nvidia-smi not found. Install NVIDIA drivers"
    exit 1
fi

echo "CUDA version:"
nvcc --version

echo -e "\nGPU devices:"
nvidia-smi --list-gpus

# Create venv
if [ ! -d "venv-gpu" ]; then
    echo -e "\nCreating virtual environment..."
    python3 -m venv venv-gpu
fi

source venv-gpu/bin/activate

# Install dependencies
echo -e "\nInstalling dependencies..."
pip install --upgrade pip
pip install cupy-cuda12x numpy

# Install KATO deps
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Verify
echo -e "\nVerifying installation..."
python -c "import cupy as cp; print(f'✓ CuPy {cp.__version__} installed')"
python -c "import cupy as cp; print(f'✓ {cp.cuda.runtime.getDeviceCount()} GPU(s) detected')"

echo -e "\n✅ GPU development environment ready!"
echo "Activate with: source venv-gpu/bin/activate"
```

Make executable:
```bash
chmod +x scripts/setup_gpu_dev.sh
```

**Acceptance Criteria:**
- ✅ CUDA detected
- ✅ CuPy imports successfully
- ✅ GPU accessible from Python
- ✅ Setup script runs without errors

---

### **Task 1.2: Baseline Performance Benchmarks** (Day 2-3)

**Goal:** Measure current pattern matching performance

#### **Create Benchmark Suite**

**File:** `benchmarks/baseline.py`

```python
#!/usr/bin/env python3
"""
Baseline performance benchmarks for KATO pattern matching.

Measures current performance before GPU optimization.
Results stored in benchmarks/results/baseline_YYYYMMDD.json
"""

import json
import time
from datetime import datetime
from itertools import chain
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
from pymongo import MongoClient

# Import KATO components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from kato.searches.pattern_search import PatternSearcher
from kato.representations.pattern import Pattern


class BenchmarkRunner:
    """Run pattern matching benchmarks."""

    def __init__(self, processor_id: str = "benchmark"):
        self.processor_id = processor_id
        self.results = {
            "benchmark_id": f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "processor_id": processor_id,
            "timestamp": datetime.now().isoformat(),
            "system_info": self._get_system_info(),
            "tests": []
        }

    def _get_system_info(self) -> Dict[str, Any]:
        """Collect system information."""
        import platform
        import psutil

        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "memory_gb": psutil.virtual_memory().total / 1e9,
            "cpu_model": platform.processor()
        }

    def generate_test_patterns(self, count: int, min_length: int = 5,
                               max_length: int = 20) -> List[Pattern]:
        """Generate random test patterns."""
        patterns = []

        # Vocabulary of test symbols
        vocab = [f"sym{i}" for i in range(100)]
        vocab += [f"VCTR|{i:04x}" for i in range(50)]

        for i in range(count):
            # Random number of events (2-5)
            num_events = np.random.randint(2, 6)

            # Random symbols per event
            events = []
            for _ in range(num_events):
                event_length = np.random.randint(min_length, max_length + 1)
                event = list(np.random.choice(vocab, event_length, replace=False))
                events.append(event)

            pattern = Pattern(events)
            patterns.append(pattern)

        return patterns

    def benchmark_query(self, pattern_count: int, query_length: int,
                       iterations: int = 10) -> Dict[str, Any]:
        """
        Benchmark pattern matching query performance.

        Args:
            pattern_count: Number of patterns to match against
            query_length: Length of query sequence
            iterations: Number of test iterations

        Returns:
            Benchmark results dict
        """
        print(f"\n{'='*60}")
        print(f"Benchmarking: {pattern_count:,} patterns, query length {query_length}")
        print(f"{'='*60}")

        # Generate test patterns
        print(f"Generating {pattern_count:,} test patterns...")
        patterns = self.generate_test_patterns(pattern_count)

        # Store in MongoDB
        print("Storing patterns in MongoDB...")
        mongo_client = MongoClient("mongodb://localhost:27017")
        kb = mongo_client[self.processor_id]

        # Clear existing
        kb.patterns_kb.delete_many({})
        kb.symbols_kb.delete_many({})
        kb.metadata.delete_many({})

        # Insert patterns
        for pattern in patterns:
            kb.patterns_kb.insert_one({
                "name": pattern.name,
                "pattern_data": pattern.pattern_data,
                "frequency": 1,
                "length": len(list(chain(*pattern.pattern_data)))
            })

        # Create searcher
        print("Initializing pattern searcher...")
        searcher = PatternSearcher(
            kb_id=self.processor_id,
            max_predictions=100,
            recall_threshold=0.1
        )

        # Generate query
        vocab = [f"sym{i}" for i in range(100)]
        query_state = list(np.random.choice(vocab, query_length, replace=False))

        print(f"Query: {query_state[:10]}{'...' if len(query_state) > 10 else ''}")

        # Warmup
        print("Warming up...")
        for _ in range(3):
            searcher.causalBelief(query_state, stm_events=None)

        # Benchmark
        print(f"Running {iterations} iterations...")
        latencies = []

        for i in range(iterations):
            start = time.perf_counter()
            results = searcher.causalBelief(query_state, stm_events=None)
            latency = (time.perf_counter() - start) * 1000  # Convert to ms
            latencies.append(latency)

            print(f"  Iteration {i+1}/{iterations}: {latency:.2f}ms ({len(results)} matches)")

        # Calculate statistics
        latencies_np = np.array(latencies)
        result = {
            "pattern_count": pattern_count,
            "query_length": query_length,
            "iterations": iterations,
            "latency_ms": {
                "min": float(latencies_np.min()),
                "max": float(latencies_np.max()),
                "mean": float(latencies_np.mean()),
                "median": float(np.median(latencies_np)),
                "p95": float(np.percentile(latencies_np, 95)),
                "p99": float(np.percentile(latencies_np, 99)),
                "std": float(latencies_np.std())
            },
            "throughput": {
                "patterns_per_second": pattern_count / (latencies_np.mean() / 1000),
                "queries_per_second": 1000 / latencies_np.mean()
            }
        }

        print(f"\nResults:")
        print(f"  Mean latency: {result['latency_ms']['mean']:.2f}ms")
        print(f"  P95 latency: {result['latency_ms']['p95']:.2f}ms")
        print(f"  Throughput: {result['throughput']['patterns_per_second']:.0f} patterns/sec")

        # Cleanup
        kb.patterns_kb.delete_many({})
        mongo_client.close()

        return result

    def benchmark_learning(self, count: int = 1000) -> Dict[str, Any]:
        """Benchmark pattern learning performance."""
        print(f"\n{'='*60}")
        print(f"Benchmarking: Learning {count} patterns")
        print(f"{'='*60}")

        # Generate patterns
        patterns = self.generate_test_patterns(count)

        # Setup MongoDB
        mongo_client = MongoClient("mongodb://localhost:27017")
        kb = mongo_client[self.processor_id]
        kb.patterns_kb.delete_many({})

        # Create searcher
        searcher = PatternSearcher(
            kb_id=self.processor_id,
            max_predictions=100,
            recall_threshold=0.1
        )

        # Benchmark learning
        print(f"Learning {count} patterns...")
        latencies = []

        for i, pattern in enumerate(patterns):
            start = time.perf_counter()

            # Store in MongoDB
            kb.patterns_kb.insert_one({
                "name": pattern.name,
                "pattern_data": pattern.pattern_data,
                "frequency": 1,
                "length": len(list(chain(*pattern.pattern_data)))
            })

            # Add to searcher indices
            flattened = list(chain(*pattern.pattern_data))
            searcher.assignNewlyLearnedToWorkers(0, pattern.name, flattened)

            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)

            if (i + 1) % 100 == 0:
                print(f"  Learned {i+1}/{count} patterns (avg: {np.mean(latencies[-100:]):.3f}ms)")

        latencies_np = np.array(latencies)
        result = {
            "pattern_count": count,
            "latency_ms": {
                "min": float(latencies_np.min()),
                "max": float(latencies_np.max()),
                "mean": float(latencies_np.mean()),
                "median": float(np.median(latencies_np)),
                "p95": float(np.percentile(latencies_np, 95)),
                "p99": float(np.percentile(latencies_np, 99))
            },
            "throughput": {
                "patterns_per_second": 1000 / latencies_np.mean()
            }
        }

        print(f"\nResults:")
        print(f"  Mean latency: {result['latency_ms']['mean']:.3f}ms")
        print(f"  Throughput: {result['throughput']['patterns_per_second']:.0f} patterns/sec")

        # Cleanup
        kb.patterns_kb.delete_many({})
        mongo_client.close()

        return result

    def run_all_benchmarks(self):
        """Run complete benchmark suite."""
        print("="*60)
        print("KATO Pattern Matching Baseline Benchmarks")
        print("="*60)

        # Query benchmarks - various pattern counts
        test_configs = [
            (1_000, 10),
            (10_000, 10),
            (100_000, 10),
            (1_000_000, 10),
        ]

        for pattern_count, query_length in test_configs:
            result = self.benchmark_query(pattern_count, query_length, iterations=5)
            self.results["tests"].append({
                "test_type": "query",
                "result": result
            })

        # Learning benchmark
        learning_result = self.benchmark_learning(count=1000)
        self.results["tests"].append({
            "test_type": "learning",
            "result": learning_result
        })

        # Save results
        output_dir = Path("benchmarks/results")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"Benchmarks complete!")
        print(f"Results saved to: {output_file}")
        print(f"{'='*60}")

        return self.results


def main():
    """Run benchmark suite."""
    runner = BenchmarkRunner(processor_id="benchmark_baseline")
    results = runner.run_all_benchmarks()

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for test in results["tests"]:
        if test["test_type"] == "query":
            r = test["result"]
            print(f"\nQuery ({r['pattern_count']:,} patterns):")
            print(f"  Mean: {r['latency_ms']['mean']:.2f}ms")
            print(f"  P95:  {r['latency_ms']['p95']:.2f}ms")
        elif test["test_type"] == "learning":
            r = test["result"]
            print(f"\nLearning ({r['pattern_count']:,} patterns):")
            print(f"  Mean: {r['latency_ms']['mean']:.3f}ms per pattern")


if __name__ == "__main__":
    main()
```

**Run Benchmarks:**
```bash
# Ensure services running
./start.sh

# Run baseline benchmarks
python benchmarks/baseline.py

# Results saved to: benchmarks/results/baseline_YYYYMMDD_HHMMSS.json
```

**Expected Results:**
- 1K patterns: ~100ms
- 10K patterns: ~1,000ms
- 100K patterns: ~10,000ms
- 1M patterns: ~100,000ms (100 seconds!)

**Acceptance Criteria:**
- ✅ Benchmarks run successfully
- ✅ Results saved to JSON
- ✅ Clear performance baseline established
- ✅ Bottlenecks identified

---

### **Task 1.3: Symbol Vocabulary Encoder** (Day 4-6)

**Goal:** Implement string-to-integer encoding for GPU

#### **Implementation**

**File:** `kato/gpu/__init__.py`
```python
"""GPU acceleration module for KATO pattern matching."""

__version__ = "0.1.0"

from .encoder import SymbolVocabularyEncoder

__all__ = ["SymbolVocabularyEncoder"]
```

**File:** `kato/gpu/encoder.py`
```python
"""
Symbol Vocabulary Encoder for GPU Pattern Matching.

Converts string symbols to integer IDs for efficient GPU processing.
Maintains bidirectional mapping with MongoDB persistence.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
from pymongo.collection import Collection

logger = logging.getLogger('kato.gpu.encoder')


class SymbolVocabularyEncoder:
    """
    Bidirectional mapping between string symbols and integer IDs.

    Attributes:
        symbol_to_id: Dict mapping symbols to integer IDs
        id_to_symbol: Dict mapping integer IDs to symbols
        vocab_size: Number of unique symbols
        next_id: Next available ID for new symbols
    """

    def __init__(self, mongodb_metadata: Collection):
        """
        Initialize encoder with MongoDB backend.

        Args:
            mongodb_metadata: MongoDB metadata collection for persistence
        """
        self.mongodb = mongodb_metadata
        self.symbol_to_id: Dict[str, int] = {}
        self.id_to_symbol: Dict[int, str] = {}
        self.next_id: int = 0

        # Load existing vocabulary
        self._load_vocabulary()

        logger.info(f"Encoder initialized with {self.vocab_size} symbols")

    @property
    def vocab_size(self) -> int:
        """Get current vocabulary size."""
        return len(self.symbol_to_id)

    def _load_vocabulary(self):
        """Load vocabulary from MongoDB."""
        vocab_doc = self.mongodb.find_one({"class": "gpu_vocabulary"})

        if vocab_doc:
            # Load existing vocabulary
            self.symbol_to_id = vocab_doc['symbol_to_id']
            self.id_to_symbol = {int(k): v for k, v in vocab_doc['id_to_symbol'].items()}
            self.next_id = vocab_doc['next_id']
            logger.info(f"Loaded vocabulary: {self.vocab_size} symbols")
        else:
            # Initialize empty vocabulary
            logger.info("No existing vocabulary found, starting fresh")

    def _save_vocabulary(self):
        """Persist vocabulary to MongoDB."""
        self.mongodb.update_one(
            {"class": "gpu_vocabulary"},
            {
                "$set": {
                    "symbol_to_id": self.symbol_to_id,
                    "id_to_symbol": {str(k): v for k, v in self.id_to_symbol.items()},
                    "vocab_size": self.vocab_size,
                    "next_id": self.next_id
                }
            },
            upsert=True
        )

    def encode_symbol(self, symbol: str) -> int:
        """
        Encode a single symbol to integer ID.

        Args:
            symbol: String symbol to encode

        Returns:
            Integer ID for the symbol
        """
        if symbol not in self.symbol_to_id:
            # Add new symbol
            self.symbol_to_id[symbol] = self.next_id
            self.id_to_symbol[self.next_id] = symbol
            self.next_id += 1

            # Persist (TODO: batch these for performance)
            self._save_vocabulary()

            logger.debug(f"Added new symbol: '{symbol}' -> {self.next_id - 1}")

        return self.symbol_to_id[symbol]

    def decode_symbol(self, symbol_id: int) -> Optional[str]:
        """
        Decode integer ID back to symbol.

        Args:
            symbol_id: Integer ID to decode

        Returns:
            String symbol, or None if ID not found
        """
        return self.id_to_symbol.get(symbol_id)

    def encode_sequence(self, sequence: List[str]) -> np.ndarray:
        """
        Encode a sequence of symbols to integer array.

        Args:
            sequence: List of string symbols

        Returns:
            NumPy array of integer IDs (int32)
        """
        encoded = [self.encode_symbol(s) for s in sequence]
        return np.array(encoded, dtype=np.int32)

    def decode_sequence(self, encoded: np.ndarray) -> List[str]:
        """
        Decode integer array back to symbols.

        Args:
            encoded: NumPy array of integer IDs

        Returns:
            List of string symbols (filters out padding -1)
        """
        symbols = []
        for symbol_id in encoded:
            if symbol_id >= 0:  # Skip padding
                symbol = self.decode_symbol(int(symbol_id))
                if symbol:
                    symbols.append(symbol)
        return symbols

    def build_from_patterns(self, patterns_collection: Collection):
        """
        Build vocabulary from existing patterns in MongoDB.

        Scans all patterns and creates mappings for all unique symbols.
        Uses deterministic ordering (alphabetically sorted).

        Args:
            patterns_collection: MongoDB patterns_kb collection
        """
        logger.info("Building vocabulary from patterns...")

        # Aggregate unique symbols
        pipeline = [
            {"$project": {"pattern_data": 1}},
            {"$unwind": "$pattern_data"},
            {"$unwind": "$pattern_data"},
            {"$group": {"_id": "$pattern_data"}},
            {"$sort": {"_id": 1}}  # Alphabetical order (deterministic)
        ]

        unique_symbols = patterns_collection.aggregate(pipeline)

        # Assign IDs
        for doc in unique_symbols:
            symbol = doc['_id']
            if symbol not in self.symbol_to_id:
                self.symbol_to_id[symbol] = self.next_id
                self.id_to_symbol[self.next_id] = symbol
                self.next_id += 1

        # Save
        self._save_vocabulary()

        logger.info(f"Built vocabulary: {self.vocab_size} unique symbols")

    def clear(self):
        """Clear vocabulary and reset to empty state."""
        self.symbol_to_id.clear()
        self.id_to_symbol.clear()
        self.next_id = 0
        self._save_vocabulary()
        logger.info("Vocabulary cleared")
```

**Acceptance Criteria:**
- ✅ Encoder class implemented
- ✅ MongoDB persistence working
- ✅ Bidirectional encoding/decoding
- ✅ New symbols handled dynamically
- ✅ Deterministic ordering (alphabetical)

---

### **Task 1.4: Test Infrastructure** (Day 7-8)

**Goal:** Create comprehensive test suite for encoder

#### **Test Data Generators**

**File:** `tests/tests/gpu/data_generators.py`
```python
"""Test data generators for GPU tests."""

import numpy as np
from itertools import chain
from typing import List, Tuple


def generate_random_patterns(
    count: int,
    min_events: int = 2,
    max_events: int = 5,
    min_symbols_per_event: int = 3,
    max_symbols_per_event: int = 10
) -> List[List[List[str]]]:
    """
    Generate random patterns for testing.

    Returns:
        List of patterns, where each pattern is a list of events,
        and each event is a list of symbols.
    """
    vocab = [f"sym{i}" for i in range(100)]
    vocab += [f"VCTR|{i:04x}" for i in range(50)]

    patterns = []
    for _ in range(count):
        num_events = np.random.randint(min_events, max_events + 1)
        pattern = []

        for _ in range(num_events):
            num_symbols = np.random.randint(min_symbols_per_event, max_symbols_per_event + 1)
            event = list(np.random.choice(vocab, num_symbols, replace=False))
            pattern.append(event)

        patterns.append(pattern)

    return patterns


def generate_test_symbols(count: int = 100) -> List[str]:
    """Generate list of test symbols."""
    symbols = []

    # Regular symbols
    symbols.extend([f"sym{i}" for i in range(count // 2)])

    # Vector symbols
    symbols.extend([f"VCTR|{i:04x}" for i in range(count // 2)])

    return symbols


def flatten_pattern(pattern: List[List[str]]) -> List[str]:
    """Flatten pattern events into single list."""
    return list(chain(*pattern))
```

#### **Encoder Unit Tests**

**File:** `tests/tests/gpu/test_encoder.py`
```python
"""Unit tests for SymbolVocabularyEncoder."""

import pytest
import numpy as np
from pymongo import MongoClient

from kato.gpu.encoder import SymbolVocabularyEncoder
from tests.tests.gpu.data_generators import generate_test_symbols


@pytest.fixture
def mongodb():
    """MongoDB test database."""
    client = MongoClient("mongodb://localhost:27017")
    db = client["test_gpu_encoder"]

    # Clear before test
    db.metadata.delete_many({})

    yield db

    # Cleanup
    db.metadata.delete_many({})
    client.close()


@pytest.fixture
def encoder(mongodb):
    """Create encoder instance."""
    return SymbolVocabularyEncoder(mongodb.metadata)


def test_encode_single_symbol(encoder):
    """Test encoding a single symbol."""
    symbol_id = encoder.encode_symbol("test_symbol")

    assert isinstance(symbol_id, int)
    assert symbol_id >= 0
    assert encoder.vocab_size == 1


def test_encode_decode_roundtrip(encoder):
    """Test encoding and decoding preserve symbol."""
    original = "test_symbol"

    symbol_id = encoder.encode_symbol(original)
    decoded = encoder.decode_symbol(symbol_id)

    assert decoded == original


def test_consistent_encoding(encoder):
    """Test same symbol always gets same ID."""
    id1 = encoder.encode_symbol("test")
    id2 = encoder.encode_symbol("test")

    assert id1 == id2


def test_different_symbols_different_ids(encoder):
    """Test different symbols get different IDs."""
    id1 = encoder.encode_symbol("symbol1")
    id2 = encoder.encode_symbol("symbol2")

    assert id1 != id2


def test_encode_sequence(encoder):
    """Test encoding a sequence of symbols."""
    sequence = ["a", "b", "c", "d"]
    encoded = encoder.encode_sequence(sequence)

    assert isinstance(encoded, np.ndarray)
    assert encoded.dtype == np.int32
    assert len(encoded) == len(sequence)
    assert all(encoded >= 0)


def test_decode_sequence(encoder):
    """Test decoding a sequence."""
    original = ["a", "b", "c", "d"]

    encoded = encoder.encode_sequence(original)
    decoded = encoder.decode_sequence(encoded)

    assert decoded == original


def test_persistence(mongodb):
    """Test vocabulary persists to MongoDB."""
    # Create encoder and add symbols
    encoder1 = SymbolVocabularyEncoder(mongodb.metadata)
    encoder1.encode_symbol("symbol1")
    encoder1.encode_symbol("symbol2")

    # Create new encoder (should load saved vocab)
    encoder2 = SymbolVocabularyEncoder(mongodb.metadata)

    assert encoder2.vocab_size == 2
    assert encoder2.encode_symbol("symbol1") == encoder1.encode_symbol("symbol1")
    assert encoder2.encode_symbol("symbol2") == encoder1.encode_symbol("symbol2")


def test_padding_filtered(encoder):
    """Test that padding (-1) is filtered in decoding."""
    sequence = ["a", "b", "c"]
    encoded = encoder.encode_sequence(sequence)

    # Add padding
    padded = np.pad(encoded, (0, 5), constant_values=-1)

    # Decode should filter padding
    decoded = encoder.decode_sequence(padded)

    assert decoded == sequence


def test_large_vocabulary(encoder):
    """Test with large vocabulary."""
    symbols = generate_test_symbols(1000)

    # Encode all
    for symbol in symbols:
        encoder.encode_symbol(symbol)

    assert encoder.vocab_size == 1000

    # Verify all encodings unique
    ids = [encoder.encode_symbol(s) for s in symbols]
    assert len(set(ids)) == 1000


def test_special_characters(encoder):
    """Test encoding symbols with special characters."""
    symbols = [
        "hello|world",
        "VCTR|abc123",
        "sym_with_underscore",
        "sym-with-dash",
        "sym.with.dots"
    ]

    for symbol in symbols:
        symbol_id = encoder.encode_symbol(symbol)
        decoded = encoder.decode_symbol(symbol_id)
        assert decoded == symbol


def test_empty_sequence(encoder):
    """Test encoding empty sequence."""
    encoded = encoder.encode_sequence([])

    assert len(encoded) == 0
    assert encoded.dtype == np.int32


def test_clear(encoder):
    """Test clearing vocabulary."""
    encoder.encode_symbol("test1")
    encoder.encode_symbol("test2")

    assert encoder.vocab_size == 2

    encoder.clear()

    assert encoder.vocab_size == 0
    assert len(encoder.symbol_to_id) == 0
    assert len(encoder.id_to_symbol) == 0
```

**Run Tests:**
```bash
pytest tests/tests/gpu/test_encoder.py -v
```

**Acceptance Criteria:**
- ✅ All tests pass
- ✅ >90% code coverage
- ✅ Edge cases covered

---

## ✅ Phase 1 Completion Checklist

**Before moving to Phase 2:**

- [ ] GPU development environment working
- [ ] CUDA/CuPy installed and verified
- [ ] Baseline benchmarks run and documented
- [ ] Results show clear performance targets (10,000ms for 1M patterns)
- [ ] Symbol encoder implemented
- [ ] Encoder unit tests pass (>90% coverage)
- [ ] Test data generators created
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] Branch merged to main

**Deliverables:**
- [ ] `benchmarks/baseline.py` - Benchmark suite
- [ ] `benchmarks/results/baseline_YYYYMMDD.json` - Baseline results
- [ ] `kato/gpu/encoder.py` - Symbol encoder
- [ ] `tests/tests/gpu/test_encoder.py` - Encoder tests
- [ ] `tests/tests/gpu/data_generators.py` - Test utilities
- [ ] `scripts/setup_gpu_dev.sh` - Setup script

---

## 🎯 Success Metrics

**Phase 1 is successful when:**
1. ✅ Clear performance baseline established
2. ✅ 10,000ms latency for 1M patterns measured
3. ✅ GPU environment operational
4. ✅ Encoder working and tested
5. ✅ Ready to start Phase 2 (CPU optimization)

---

## 📞 Need Help?

**Stuck? Check:**
1. `docs/gpu/QUICK_START.md` - Common issues
2. `docs/gpu/IMPLEMENTATION_PLAN.md` - Full context
3. Test cases for examples
4. KATO source code for patterns

**Next:** `docs/gpu/PHASE2_GUIDE.md` (CPU optimization)
