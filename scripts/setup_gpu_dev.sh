#!/bin/bash
set -e

echo "======================================"
echo "KATO GPU Development Environment Setup"
echo "======================================"
echo ""

# Check CUDA
echo "1. Checking CUDA Toolkit..."
if ! command -v nvcc &> /dev/null; then
    echo "❌ ERROR: CUDA Toolkit not found (nvcc command missing)"
    echo ""
    echo "Please install CUDA Toolkit 12.x from:"
    echo "https://developer.nvidia.com/cuda-downloads"
    echo ""
    exit 1
fi

CUDA_VERSION=$(nvcc --version | grep "release" | sed -n 's/.*release \([0-9]*\.[0-9]*\).*/\1/p')
echo "✓ CUDA Toolkit detected: version $CUDA_VERSION"
echo ""

# Check GPU
echo "2. Checking GPU availability..."
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ ERROR: nvidia-smi not found"
    echo ""
    echo "Please install NVIDIA drivers:"
    echo "  Ubuntu/Debian: sudo apt install nvidia-driver-535"
    echo "  Or download from: https://www.nvidia.com/Download/index.aspx"
    echo ""
    exit 1
fi

echo "✓ NVIDIA drivers detected"
echo ""
echo "GPU Information:"
nvidia-smi --list-gpus
echo ""

# Check GPU memory
GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1)
GPU_MEMORY_GB=$(echo "scale=1; $GPU_MEMORY / 1024" | bc)
echo "GPU Memory: ${GPU_MEMORY_GB}GB"

if (( $(echo "$GPU_MEMORY_GB < 6.0" | bc -l) )); then
    echo "⚠️  WARNING: GPU has less than 6GB VRAM. Minimum 6GB recommended for 10M patterns."
    echo "   Your GPU may work but with reduced capacity."
    echo ""
fi

# Create virtual environment
echo "3. Setting up Python virtual environment..."
if [ ! -d "venv-gpu" ]; then
    echo "Creating venv-gpu..."
    python3 -m venv venv-gpu
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "4. Activating virtual environment..."
source venv-gpu/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "5. Upgrading pip..."
pip install --upgrade pip --quiet
echo "✓ pip upgraded"
echo ""

# Install CuPy
echo "6. Installing CuPy..."
echo "Detecting CUDA version for CuPy installation..."

CUDA_MAJOR=$(echo $CUDA_VERSION | cut -d. -f1)
CUDA_MINOR=$(echo $CUDA_VERSION | cut -d. -f2)

if [ "$CUDA_MAJOR" = "12" ]; then
    echo "Installing cupy-cuda12x for CUDA 12.x..."
    pip install cupy-cuda12x --quiet
elif [ "$CUDA_MAJOR" = "11" ]; then
    echo "Installing cupy-cuda11x for CUDA 11.x..."
    pip install cupy-cuda11x --quiet
else
    echo "⚠️  WARNING: Unsupported CUDA version $CUDA_VERSION"
    echo "   Attempting to install cupy-cuda12x..."
    pip install cupy-cuda12x --quiet
fi
echo "✓ CuPy installed"
echo ""

# Install NumPy (required for CuPy)
echo "7. Installing NumPy..."
pip install numpy --quiet
echo "✓ NumPy installed"
echo ""

# Install KATO dependencies
echo "8. Installing KATO dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt --quiet
    echo "✓ KATO dependencies installed"
else
    echo "⚠️  WARNING: requirements.txt not found, skipping KATO dependencies"
fi
echo ""

# Install test dependencies
if [ -f "tests/requirements.txt" ]; then
    pip install -r tests/requirements.txt --quiet
    echo "✓ Test dependencies installed"
    echo ""
fi

# Verify installation
echo "9. Verifying installation..."
echo ""

# Test CuPy
python3 -c "import cupy as cp; print(f'✓ CuPy {cp.__version__} imported successfully')" || {
    echo "❌ ERROR: CuPy import failed"
    exit 1
}

# Test GPU access
GPU_COUNT=$(python3 -c "import cupy as cp; print(cp.cuda.runtime.getDeviceCount())" 2>/dev/null)
if [ "$GPU_COUNT" -gt 0 ]; then
    echo "✓ $GPU_COUNT GPU(s) accessible from Python"
else
    echo "❌ ERROR: No GPUs accessible from Python"
    exit 1
fi

# Test NumPy
python3 -c "import numpy as np; print(f'✓ NumPy {np.__version__} imported successfully')" || {
    echo "❌ ERROR: NumPy import failed"
    exit 1
}

echo ""
echo "======================================"
echo "✅ GPU Development Environment Ready!"
echo "======================================"
echo ""
echo "GPU Configuration:"
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader
echo ""
echo "To activate the environment:"
echo "  source venv-gpu/bin/activate"
echo ""
echo "Next steps:"
echo "  1. Run baseline benchmarks: python benchmarks/baseline.py"
echo "  2. Run GPU tests: pytest tests/tests/gpu/ -v"
echo ""
