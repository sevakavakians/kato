#!/bin/bash
set -e

# KATO Installer
# Downloads and extracts the KATO deployment bundle from GitHub Releases.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/sevakavakians/kato/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/sevakavakians/kato/main/install.sh | bash -s -- --dir /opt/kato
#   curl -fsSL https://raw.githubusercontent.com/sevakavakians/kato/main/install.sh | bash -s -- --version v3.7.0

REPO="sevakavakians/kato"
INSTALL_DIR="./kato"
VERSION=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

usage() {
    echo "KATO Installer"
    echo ""
    echo "Usage:"
    echo "  curl -fsSL https://raw.githubusercontent.com/${REPO}/main/install.sh | bash"
    echo "  curl -fsSL https://raw.githubusercontent.com/${REPO}/main/install.sh | bash -s -- [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dir <path>       Installation directory (default: ./kato)"
    echo "  --version <tag>    Install specific version, e.g. v3.7.0 (default: latest)"
    echo "  --help             Show this help message"
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Check dependencies
for cmd in curl tar; do
    if ! command -v "$cmd" &> /dev/null; then
        echo -e "${RED}Error: '$cmd' is required but not found${NC}"
        exit 1
    fi
done

# Cleanup on failure
TMPDIR_CREATED=""
cleanup() {
    if [[ -n "$TMPDIR_CREATED" && -d "$TMPDIR_CREATED" ]]; then
        rm -rf "$TMPDIR_CREATED"
    fi
}
trap cleanup EXIT

echo -e "${BLUE}KATO Installer${NC}"
echo ""

# Determine release URL
if [[ -z "$VERSION" ]]; then
    echo "Finding latest release..."
    RELEASE_URL="https://api.github.com/repos/${REPO}/releases/latest"
else
    echo "Finding release ${VERSION}..."
    RELEASE_URL="https://api.github.com/repos/${REPO}/releases/tags/${VERSION}"
fi

# Fetch release info and extract the deployment tarball URL
RELEASE_JSON=$(curl -fsSL "$RELEASE_URL") || {
    echo -e "${RED}Error: Could not fetch release info from GitHub${NC}"
    if [[ -n "$VERSION" ]]; then
        echo "Check that version '${VERSION}' exists at: https://github.com/${REPO}/releases"
    else
        echo "No releases found at: https://github.com/${REPO}/releases"
    fi
    exit 1
}

# Extract the deployment tarball download URL (no jq dependency)
TARBALL_URL=$(echo "$RELEASE_JSON" | grep -o '"browser_download_url"[[:space:]]*:[[:space:]]*"[^"]*kato-deployment-[^"]*\.tar\.gz"' | head -1 | grep -o 'https://[^"]*')

if [[ -z "$TARBALL_URL" ]]; then
    echo -e "${RED}Error: No deployment bundle found in the release${NC}"
    echo "The release may not include a deployment tarball."
    echo "Check: https://github.com/${REPO}/releases"
    exit 1
fi

# Extract version from URL for display
DISPLAY_VERSION=$(echo "$TARBALL_URL" | grep -o 'v[0-9][0-9.]*' | head -1)
echo -e "Downloading KATO ${GREEN}${DISPLAY_VERSION}${NC}..."

# Create temp directory for download
TMPDIR_CREATED=$(mktemp -d)
TARBALL_PATH="${TMPDIR_CREATED}/kato-deployment.tar.gz"

# Download the tarball
curl -fsSL -o "$TARBALL_PATH" "$TARBALL_URL" || {
    echo -e "${RED}Error: Failed to download deployment bundle${NC}"
    exit 1
}

# Handle existing installation (preserve .env)
ENV_BACKUP=""
if [[ -d "$INSTALL_DIR" && -f "${INSTALL_DIR}/.env" ]]; then
    echo -e "${YELLOW}Existing installation found. Preserving .env file...${NC}"
    ENV_BACKUP="${TMPDIR_CREATED}/.env.backup"
    cp "${INSTALL_DIR}/.env" "$ENV_BACKUP"
fi

# Extract to install directory
mkdir -p "$INSTALL_DIR"
tar -xzf "$TARBALL_PATH" --strip-components=1 -C "$INSTALL_DIR"

# Restore .env if backed up
if [[ -n "$ENV_BACKUP" && -f "$ENV_BACKUP" ]]; then
    cp "$ENV_BACKUP" "${INSTALL_DIR}/.env"
    echo -e "${GREEN}Existing .env file preserved${NC}"
fi

# Make scripts executable
chmod +x "${INSTALL_DIR}/kato-manager.sh"

# Ensure config files are readable by container processes (e.g. ClickHouse UID 101)
chmod 644 "${INSTALL_DIR}/config/clickhouse/"* 2>/dev/null || true
chmod 644 "${INSTALL_DIR}/config/redis.conf" 2>/dev/null || true

echo ""
echo -e "${GREEN}KATO ${DISPLAY_VERSION} installed to ${INSTALL_DIR}${NC}"
echo ""
echo "Next steps:"
echo "  cd ${INSTALL_DIR}"
echo "  ./kato-manager.sh start"
echo ""
