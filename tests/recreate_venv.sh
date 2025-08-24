#!/bin/bash

# Script to recreate virtual environment for KATO tests
# This will force remove the old venv and create a new one

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}KATO Virtual Environment Recreation Script${NC}"
echo "==========================================="
echo ""

# Get the absolute path to the kato-tests directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Working directory: $SCRIPT_DIR"

# Change to the kato-tests directory
cd "$SCRIPT_DIR"

# Check if we're in the right directory
if [ ! -f "pytest.ini" ]; then
    echo -e "${RED}Error: Not in kato-tests directory${NC}"
    exit 1
fi

# Step 1: Remove or backup old virtual environment
echo ""
echo -e "${YELLOW}Step 1: Removing old virtual environment...${NC}"

if [ -d "venv" ]; then
    # Try to remove it
    rm -rf venv 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Old venv removed successfully"
    else
        # If removal fails, try to rename it
        BACKUP_NAME="venv_old_$(date +%s)"
        mv venv "$BACKUP_NAME" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Old venv moved to $BACKUP_NAME"
        else
            echo -e "${RED}Warning: Could not remove old venv${NC}"
            echo "You may need to manually remove it"
        fi
    fi
else
    echo "No existing venv found"
fi

# Step 2: Create new virtual environment
echo ""
echo -e "${YELLOW}Step 2: Creating new virtual environment...${NC}"

# Try different Python commands
PYTHON_CMD=""
for cmd in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python; do
    if command -v $cmd &> /dev/null; then
        # Check if it's Python 3
        VERSION=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        MAJOR_VERSION=$(echo $VERSION | cut -d. -f1)
        if [ "$MAJOR_VERSION" -ge "3" ]; then
            PYTHON_CMD=$cmd
            echo "Found Python: $cmd (version $VERSION)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}Error: Python 3 not found!${NC}"
    echo "Please install Python 3 and try again"
    exit 1
fi

# Create the virtual environment
$PYTHON_CMD -m venv venv
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to create virtual environment${NC}"
    exit 1
fi

echo "Virtual environment created successfully"

# Step 3: Activate and install dependencies
echo ""
echo -e "${YELLOW}Step 3: Installing dependencies...${NC}"

# Activate the virtual environment
source venv/bin/activate

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to activate virtual environment${NC}"
    exit 1
fi

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
if [ -f "requirements.txt" ]; then
    echo "Installing from requirements.txt..."
    pip install -r requirements.txt
else
    echo "Installing basic test dependencies..."
    pip install pytest pytest-timeout pytest-xdist requests
fi

# Step 4: Verify installation
echo ""
echo -e "${GREEN}Step 4: Verification${NC}"
echo "-------------------"

echo "Python location: $(which python)"
echo "Python version: $(python --version)"
echo "Pip location: $(which pip)"
echo "Pip version: $(pip --version)"
echo ""
echo "Test packages installed:"
pip list | grep -E "pytest|requests" | sed 's/^/  /'

# Check the pyvenv.cfg file
echo ""
echo "Virtual environment configuration:"
if [ -f "venv/pyvenv.cfg" ]; then
    grep -E "home|command" venv/pyvenv.cfg | sed 's/^/  /'
fi

# Deactivate the virtual environment
deactivate

echo ""
echo -e "${GREEN}✓ Virtual environment recreated successfully!${NC}"
echo ""
echo "To activate the virtual environment, run:"
echo "  source $SCRIPT_DIR/venv/bin/activate"
echo ""
echo "To run tests, use:"
echo "  ./run_tests.sh"
echo ""