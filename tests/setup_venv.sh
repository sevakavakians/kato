#!/bin/bash

# Script to set up virtual environment for KATO tests

echo "Setting up virtual environment for KATO tests..."

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Working in: $SCRIPT_DIR"

# Remove old venv if it exists
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "Removing old virtual environment..."
    # Try different removal methods
    rm -rf "$SCRIPT_DIR/venv" 2>/dev/null || \
    mv "$SCRIPT_DIR/venv" "$SCRIPT_DIR/venv_old_$(date +%s)" 2>/dev/null || \
    echo "Warning: Could not remove old venv, will try to overwrite"
fi

# Try to find Python 3
PYTHON_CMD=""
if command -v python3.13 &> /dev/null; then
    PYTHON_CMD="python3.13"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif [ -f "/usr/local/opt/python@3.13/bin/python3.13" ]; then
    PYTHON_CMD="/usr/local/opt/python@3.13/bin/python3.13"
elif [ -f "/usr/bin/python3" ]; then
    PYTHON_CMD="/usr/bin/python3"
else
    echo "Error: Python 3 not found!"
    echo "Please install Python 3 and try again."
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
$PYTHON_CMD --version

# Create new virtual environment
echo "Creating new virtual environment..."
$PYTHON_CMD -m venv "$SCRIPT_DIR/venv"

if [ $? -ne 0 ]; then
    echo "Error: Failed to create virtual environment"
    exit 1
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source "$SCRIPT_DIR/venv/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo "Installing requirements..."
    pip install -r "$SCRIPT_DIR/requirements.txt"
else
    echo "Warning: requirements.txt not found"
    echo "Installing basic test requirements..."
    pip install pytest pytest-timeout pytest-xdist requests
fi

# Verify installation
echo ""
echo "Verification:"
echo "-------------"
which python
python --version
which pip
pip --version
echo ""
echo "Installed packages:"
pip list | grep -E "pytest|requests"

echo ""
echo "Virtual environment setup complete!"
echo ""
echo "To use the virtual environment, run:"
echo "  source $SCRIPT_DIR/venv/bin/activate"
echo ""
echo "To run tests, use:"
echo "  ./run_tests.sh"