#!/usr/bin/env python3
"""
Setup virtual environment for KATO tests.
This script creates a new virtual environment and installs dependencies.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def main():
    """Set up virtual environment for KATO tests."""
    
    # Get the directory of this script
    script_dir = Path(__file__).parent.absolute()
    venv_dir = script_dir / "venv"
    
    print(f"Setting up virtual environment in: {script_dir}")
    print("=" * 50)
    
    # Remove old venv if it exists
    if venv_dir.exists():
        print(f"Removing old virtual environment at {venv_dir}...")
        try:
            shutil.rmtree(venv_dir)
            print("Old venv removed successfully")
        except Exception as e:
            print(f"Warning: Could not remove old venv: {e}")
            # Try to rename it
            try:
                import time
                backup_name = venv_dir.parent / f"venv_old_{int(time.time())}"
                venv_dir.rename(backup_name)
                print(f"Moved old venv to {backup_name}")
            except Exception as e2:
                print(f"Could not move old venv: {e2}")
                print("Continuing anyway...")
    
    # Create new virtual environment
    print(f"\nCreating new virtual environment...")
    try:
        import venv
        venv.create(venv_dir, with_pip=True)
        print("Virtual environment created successfully")
    except Exception as e:
        print(f"Error creating venv with venv module: {e}")
        # Try with subprocess
        try:
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
            print("Virtual environment created using subprocess")
        except Exception as e2:
            print(f"Error: Failed to create virtual environment: {e2}")
            return 1
    
    # Get paths for the new venv
    if os.name == 'nt':  # Windows
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
    else:  # Unix/Linux/Mac
        python_exe = venv_dir / "bin" / "python"
        pip_exe = venv_dir / "bin" / "pip"
    
    # Verify the virtual environment was created
    if not python_exe.exists():
        print(f"Error: Python executable not found at {python_exe}")
        return 1
    
    print(f"\nPython executable: {python_exe}")
    
    # Upgrade pip
    print("\nUpgrading pip...")
    try:
        subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        print("Pip upgraded successfully")
    except Exception as e:
        print(f"Warning: Could not upgrade pip: {e}")
    
    # Install requirements
    requirements_file = script_dir / "requirements.txt"
    if requirements_file.exists():
        print(f"\nInstalling requirements from {requirements_file}...")
        try:
            subprocess.run([str(pip_exe), "install", "-r", str(requirements_file)], check=True)
            print("Requirements installed successfully")
        except Exception as e:
            print(f"Error installing requirements: {e}")
            print("\nTrying to install basic test requirements...")
            try:
                subprocess.run([str(pip_exe), "install", "pytest", "pytest-timeout", "pytest-xdist", "requests"], check=True)
                print("Basic requirements installed")
            except Exception as e2:
                print(f"Error installing basic requirements: {e2}")
    else:
        print(f"Warning: {requirements_file} not found")
        print("Installing basic test requirements...")
        try:
            subprocess.run([str(pip_exe), "install", "pytest", "pytest-timeout", "pytest-xdist", "requests"], check=True)
            print("Basic requirements installed")
        except Exception as e:
            print(f"Error installing basic requirements: {e}")
    
    # Verify installation
    print("\n" + "=" * 50)
    print("Verification:")
    print("-" * 50)
    
    # Check Python version
    result = subprocess.run([str(python_exe), "--version"], capture_output=True, text=True)
    print(f"Python: {result.stdout.strip()}")
    
    # Check pip version
    result = subprocess.run([str(pip_exe), "--version"], capture_output=True, text=True)
    print(f"Pip: {result.stdout.strip()}")
    
    # List installed packages
    print("\nInstalled test packages:")
    result = subprocess.run([str(pip_exe), "list"], capture_output=True, text=True)
    for line in result.stdout.split('\n'):
        if any(pkg in line.lower() for pkg in ['pytest', 'requests']):
            print(f"  {line}")
    
    print("\n" + "=" * 50)
    print("Virtual environment setup complete!")
    print("")
    print("To activate the virtual environment, run:")
    if os.name == 'nt':
        print(f"  {venv_dir}\\Scripts\\activate")
    else:
        print(f"  source {venv_dir}/bin/activate")
    print("")
    print("To run tests, use:")
    print("  ./run_tests.sh")
    print("=" * 50)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())