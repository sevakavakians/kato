#!/bin/bash

echo "=== Docker Installation Diagnostic ==="
echo "======================================"
echo

echo "1. Checking Docker command availability:"
echo "---------------------------------------"
if command -v docker &> /dev/null; then
    echo "✓ Docker command found via 'command -v docker'"
    DOCKER_PATH=$(command -v docker)
    echo "  Path: $DOCKER_PATH"
else
    echo "✗ Docker command NOT found via 'command -v docker'"
fi

echo
echo "2. Checking common Docker installation paths:"
echo "--------------------------------------------"
COMMON_PATHS=(
    "/usr/bin/docker"
    "/usr/local/bin/docker"
    "/opt/homebrew/bin/docker"
    "/Applications/Docker.app/Contents/Resources/bin/docker"
    "$HOME/bin/docker"
)

for path in "${COMMON_PATHS[@]}"; do
    if [[ -x "$path" ]]; then
        echo "✓ Found Docker at: $path"
    else
        echo "✗ Not found: $path"
    fi
done

echo
echo "3. Checking Docker Desktop (macOS/Windows):"
echo "------------------------------------------"
if [[ -d "/Applications/Docker.app" ]]; then
    echo "✓ Docker Desktop app found at /Applications/Docker.app"
    if pgrep -f "Docker Desktop" > /dev/null; then
        echo "✓ Docker Desktop is running"
    else
        echo "⚠ Docker Desktop app found but may not be running"
    fi
else
    echo "✗ Docker Desktop app not found at /Applications/Docker.app"
fi

echo
echo "4. Checking PATH variable:"
echo "-------------------------"
echo "Current PATH: $PATH"
echo "PATH contains /usr/local/bin: $(echo $PATH | grep -q '/usr/local/bin' && echo 'Yes' || echo 'No')"
echo "PATH contains /opt/homebrew/bin: $(echo $PATH | grep -q '/opt/homebrew/bin' && echo 'Yes' || echo 'No')"

echo
echo "5. Checking Docker daemon:"
echo "-------------------------"
if docker version &> /dev/null; then
    echo "✓ Docker daemon is accessible"
    echo "Docker version:"
    docker version --format '  Client: {{.Client.Version}}'
    docker version --format '  Server: {{.Server.Version}}' 2>/dev/null || echo "  Server: Not accessible"
else
    echo "✗ Docker daemon is not accessible or docker command failed"
    echo "Error output:"
    docker version 2>&1 | sed 's/^/  /'
fi

echo
echo "6. Process information:"
echo "----------------------"
echo "Running as user: $(whoami)"
echo "Shell: $SHELL"
echo "Operating system: $(uname -s)"

if command -v docker &> /dev/null; then
    echo "Docker groups: $(groups | grep -o docker || echo 'Not in docker group')"
fi

echo
echo "7. Suggested fixes:"
echo "------------------"
if ! command -v docker &> /dev/null; then
    echo "Docker command not found. Try these fixes:"
    echo "  1. If using Docker Desktop:"
    echo "     - Start Docker Desktop application"
    echo "     - Wait for it to fully initialize"
    echo "     - Check that Docker icon shows 'running' status"
    echo
    echo "  2. If using Homebrew on macOS:"
    echo "     brew install docker"
    echo "     # OR for Docker Desktop:"
    echo "     brew install --cask docker"
    echo
    echo "  3. Add Docker to PATH manually:"
    echo "     export PATH=\"/Applications/Docker.app/Contents/Resources/bin:\$PATH\""
    echo "     # Add this to your ~/.bashrc or ~/.zshrc"
    echo
    echo "  4. Restart your terminal/shell after installation"
else
    if ! docker version &> /dev/null; then
        echo "Docker command found but daemon not accessible:"
        echo "  1. Start Docker Desktop (if using)"
        echo "  2. Start Docker daemon: sudo systemctl start docker (Linux)"
        echo "  3. Add user to docker group: sudo usermod -aG docker \$(whoami)"
        echo "     Then log out and back in"
    else
        echo "✓ Docker appears to be working correctly!"
        echo "  The issue might be with the kato-manager.sh script detection logic."
    fi
fi

echo
echo "=== End Diagnostic ==="