#!/bin/bash
set -e

# Version Bump Utility for KATO
# Bumps semantic version across pyproject.toml, setup.py, and kato/__init__.py
# Usage: ./bump-version.sh [major|minor|patch] ["commit message"]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check arguments
if [[ $# -lt 1 ]]; then
    echo -e "${RED}Error: Missing version bump type${NC}"
    echo "Usage: ./bump-version.sh [major|minor|patch] [\"commit message\"]"
    echo ""
    echo "Examples:"
    echo "  ./bump-version.sh patch                          # Bump patch version (2.0.0 -> 2.0.1)"
    echo "  ./bump-version.sh minor \"Add new feature\"        # Bump minor version (2.0.0 -> 2.1.0)"
    echo "  ./bump-version.sh major \"Breaking changes\"       # Bump major version (2.0.0 -> 3.0.0)"
    exit 1
fi

BUMP_TYPE=$1
COMMIT_MSG=${2:-"chore: bump version to"}

# Validate bump type
if [[ ! "$BUMP_TYPE" =~ ^(major|minor|patch)$ ]]; then
    echo -e "${RED}Error: Invalid bump type '${BUMP_TYPE}'${NC}"
    echo "Must be one of: major, minor, patch"
    exit 1
fi

# Check for uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    echo -e "${YELLOW}Warning: You have uncommitted changes${NC}"
    echo "Current git status:"
    git status --short
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted"
        exit 1
    fi
fi

# Extract current version from pyproject.toml
if [[ ! -f "pyproject.toml" ]]; then
    echo -e "${RED}Error: pyproject.toml not found${NC}"
    exit 1
fi

CURRENT_VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
if [[ -z "$CURRENT_VERSION" ]]; then
    echo -e "${RED}Error: Could not extract version from pyproject.toml${NC}"
    exit 1
fi

echo -e "${GREEN}Current version: ${CURRENT_VERSION}${NC}"

# Parse semantic version
IFS='.' read -r MAJOR MINOR PATCH <<< "${CURRENT_VERSION}"

# Handle pre-release versions
if [[ "$PATCH" == *"-"* ]]; then
    PATCH=$(echo "$PATCH" | cut -d'-' -f1)
    echo -e "${YELLOW}Note: Stripping pre-release suffix${NC}"
fi

# Bump version based on type
case $BUMP_TYPE in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
echo -e "${GREEN}New version: ${NEW_VERSION}${NC}"
echo ""

# Confirm before proceeding
read -p "Proceed with version bump? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 1
fi

# Update pyproject.toml
echo "Updating pyproject.toml..."
sed -i.bak "s/^version = \"${CURRENT_VERSION}\"/version = \"${NEW_VERSION}\"/" pyproject.toml
rm -f pyproject.toml.bak

# Update setup.py
if [[ -f "setup.py" ]]; then
    echo "Updating setup.py..."
    sed -i.bak "s/version=\"${CURRENT_VERSION}\"/version=\"${NEW_VERSION}\"/" setup.py
    rm -f setup.py.bak
fi

# Update kato/__init__.py
if [[ -f "kato/__init__.py" ]]; then
    echo "Updating kato/__init__.py..."
    sed -i.bak "s/__version__ = '${CURRENT_VERSION}'/__version__ = '${NEW_VERSION}'/" kato/__init__.py
    rm -f kato/__init__.py.bak
fi

echo ""
echo -e "${GREEN}Version bumped successfully!${NC}"
echo ""

# Show what changed
echo "Files updated:"
git diff --stat pyproject.toml setup.py kato/__init__.py 2>/dev/null || true
echo ""

# Ask about committing
read -p "Create git commit? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    FULL_COMMIT_MSG="${COMMIT_MSG} ${NEW_VERSION}"
    git add pyproject.toml setup.py kato/__init__.py
    git commit -m "$FULL_COMMIT_MSG"
    echo -e "${GREEN}Committed changes${NC}"
    echo ""

    # Ask about tagging
    read -p "Create git tag v${NEW_VERSION}? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter tag message (optional): " TAG_MSG
        if [[ -z "$TAG_MSG" ]]; then
            TAG_MSG="Release v${NEW_VERSION}"
        fi
        git tag -a "v${NEW_VERSION}" -m "$TAG_MSG"
        echo -e "${GREEN}Created tag v${NEW_VERSION}${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Push commit: git push origin main"
        echo "  2. Push tag: git push origin v${NEW_VERSION}"
        echo "  3. Build and push images: ./build-and-push.sh"
    fi
fi

echo ""
echo -e "${GREEN}Done!${NC}"
