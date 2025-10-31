#!/bin/bash
set -e

# Container Manager for KATO
# Handles version management and container image publishing after code changes
# This script should be run by the container-manager agent or manually after code changes

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BUMP_TYPE="${1:-patch}"  # Default to patch if not specified
DESCRIPTION="${2:-Code changes and improvements}"
AUTO_MODE="${AUTO_MODE:-false}"  # Set to true for non-interactive mode

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  KATO Container Manager${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Validate bump type
if [[ ! "$BUMP_TYPE" =~ ^(major|minor|patch)$ ]]; then
    echo -e "${RED}Error: Invalid bump type '${BUMP_TYPE}'${NC}"
    echo "Usage: ./container-manager.sh [major|minor|patch] [\"description\"]"
    echo ""
    echo "Examples:"
    echo "  ./container-manager.sh patch \"Fix bug in pattern matching\""
    echo "  ./container-manager.sh minor \"Add new API endpoint\""
    echo "  ./container-manager.sh major \"Breaking API changes\""
    exit 1
fi

# Check for required scripts
if [[ ! -f "bump-version.sh" ]]; then
    echo -e "${RED}Error: bump-version.sh not found${NC}"
    exit 1
fi

if [[ ! -f "build-and-push.sh" ]]; then
    echo -e "${RED}Error: build-and-push.sh not found${NC}"
    exit 1
fi

# Check git status
echo -e "${YELLOW}Checking git status...${NC}"
if [[ -n $(git status --porcelain) ]]; then
    echo -e "${YELLOW}Warning: You have uncommitted changes${NC}"
    git status --short
    echo ""

    if [[ "$AUTO_MODE" != "true" ]]; then
        read -p "Do you want to commit these changes first? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}Staging all changes...${NC}"
            git add -A

            echo -e "${BLUE}Enter commit message:${NC}"
            read -r COMMIT_MSG

            git commit -m "$COMMIT_MSG"
            echo -e "${GREEN}✓ Changes committed${NC}"
        else
            echo -e "${RED}Aborted: Please commit or stash changes first${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Error in AUTO_MODE: Uncommitted changes detected${NC}"
        exit 1
    fi
fi

# Check that we're on the main branch (or allow override)
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo -e "${YELLOW}Warning: You are on branch '${CURRENT_BRANCH}', not 'main'${NC}"

    if [[ "$AUTO_MODE" != "true" ]]; then
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborted"
            exit 1
        fi
    else
        echo -e "${RED}Error in AUTO_MODE: Not on main branch${NC}"
        exit 1
    fi
fi

# Step 1: Bump version
echo ""
echo -e "${BLUE}Step 1: Bumping version (${BUMP_TYPE})${NC}"
echo "────────────────────────────────────────────────────────────"

# Get current version before bump
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
echo -e "Current version: ${YELLOW}${CURRENT_VERSION}${NC}"

# Run bump-version.sh in automated mode
export BUMP_TYPE
export DESCRIPTION

# Create a temporary script to handle bump-version.sh automation
cat > /tmp/bump-version-auto.sh << 'EOFSCRIPT'
#!/bin/bash
set -e

# Automated version bump
BUMP_TYPE=${1:-patch}
DESCRIPTION=${2:-"Version bump"}

# Get current version
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)

# Parse semantic version
IFS='.' read -r MAJOR MINOR PATCH <<< "${CURRENT_VERSION}"

# Handle pre-release versions
if [[ "$PATCH" == *"-"* ]]; then
    PATCH=$(echo "$PATCH" | cut -d'-' -f1)
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

# Update files
sed -i.bak "s/^version = \"${CURRENT_VERSION}\"/version = \"${NEW_VERSION}\"/" pyproject.toml
rm -f pyproject.toml.bak

if [[ -f "setup.py" ]]; then
    sed -i.bak "s/version=\"${CURRENT_VERSION}\"/version=\"${NEW_VERSION}\"/" setup.py
    rm -f setup.py.bak
fi

if [[ -f "kato/__init__.py" ]]; then
    sed -i.bak "s/__version__ = '${CURRENT_VERSION}'/__version__ = '${NEW_VERSION}'/" kato/__init__.py
    rm -f kato/__init__.py.bak
fi

# Commit changes
git add pyproject.toml setup.py kato/__init__.py
git commit -m "chore: bump version to ${NEW_VERSION}"

# Create tag
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}: ${DESCRIPTION}"

echo "${NEW_VERSION}"
EOFSCRIPT

chmod +x /tmp/bump-version-auto.sh
NEW_VERSION=$(/tmp/bump-version-auto.sh "$BUMP_TYPE" "$DESCRIPTION")
rm /tmp/bump-version-auto.sh

echo -e "${GREEN}✓ Version bumped to: ${NEW_VERSION}${NC}"

# Step 2: Update CHANGELOG
echo ""
echo -e "${BLUE}Step 2: Updating CHANGELOG${NC}"
echo "────────────────────────────────────────────────────────────"

if [[ -f "CHANGELOG.md" ]]; then
    # Get today's date
    TODAY=$(date +"%Y-%m-%d")

    # Check if there are unreleased changes
    if grep -q "\[Unreleased\]" CHANGELOG.md; then
        # Add new version section after [Unreleased]
        # This is a simple placeholder - in real usage, manually curate the changelog
        echo -e "${YELLOW}Note: CHANGELOG.md should be manually updated with release notes${NC}"
        echo -e "${YELLOW}Unreleased changes should be moved to [${NEW_VERSION}] section${NC}"
    fi

    echo -e "${GREEN}✓ CHANGELOG.md found (manual update recommended)${NC}"
else
    echo -e "${YELLOW}Warning: CHANGELOG.md not found${NC}"
fi

# Step 3: Push changes to remote
echo ""
echo -e "${BLUE}Step 3: Pushing changes to remote${NC}"
echo "────────────────────────────────────────────────────────────"

echo "Pushing commit and tag to remote..."
git push origin "$CURRENT_BRANCH"
git push origin "v${NEW_VERSION}"

echo -e "${GREEN}✓ Changes and tag pushed to remote${NC}"

# Step 4: Build container images
echo ""
echo -e "${BLUE}Step 4: Building container images${NC}"
echo "────────────────────────────────────────────────────────────"

# Check if logged into container registry
if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo "Building multi-tag images..."
./build-and-push.sh

echo -e "${GREEN}✓ Container images built and pushed${NC}"

# Step 5: Verify deployment
echo ""
echo -e "${BLUE}Step 5: Verification${NC}"
echo "────────────────────────────────────────────────────────────"

# Check if image exists in registry
echo "Verifying images in registry..."
echo "  - ghcr.io/sevakavakians/kato:${NEW_VERSION}"
echo "  - ghcr.io/sevakavakians/kato:latest"

# Try to inspect the image
if docker manifest inspect "ghcr.io/sevakavakians/kato:${NEW_VERSION}" &> /dev/null; then
    echo -e "${GREEN}✓ Image verified in registry${NC}"
else
    echo -e "${YELLOW}⚠ Could not verify image (may need time to propagate)${NC}"
fi

# Summary
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Container Manager Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Summary:"
echo "  • Version: ${CURRENT_VERSION} → ${NEW_VERSION}"
echo "  • Bump type: ${BUMP_TYPE}"
echo "  • Description: ${DESCRIPTION}"
echo "  • Git tag: v${NEW_VERSION}"
echo "  • Container images: ghcr.io/sevakavakians/kato:${NEW_VERSION}"
echo ""
echo "Next steps:"
echo "  1. Update CHANGELOG.md with detailed release notes (if not done)"
echo "  2. Create GitHub release at: https://github.com/sevakavakians/kato/releases/new?tag=v${NEW_VERSION}"
echo "  3. Update deployment documentation if needed"
echo "  4. Notify users of the new release"
echo ""
echo "Users can now pull the new version:"
echo "  docker pull ghcr.io/sevakavakians/kato:${NEW_VERSION}"
echo "  docker pull ghcr.io/sevakavakians/kato:latest"
echo ""
