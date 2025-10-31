#!/bin/bash
set -e

# Container Image Build and Push Script for KATO
# Builds multi-tagged Docker images with semantic versioning
# Usage: ./build-and-push.sh [--no-push] [--registry REGISTRY]

# Configuration
IMAGE_NAME="ghcr.io/sevakavakians/kato"
NO_PUSH=false
CUSTOM_REGISTRY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-push)
            NO_PUSH=true
            shift
            ;;
        --registry)
            CUSTOM_REGISTRY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./build-and-push.sh [--no-push] [--registry REGISTRY]"
            exit 1
            ;;
    esac
done

# Use custom registry if provided
if [[ -n "$CUSTOM_REGISTRY" ]]; then
    IMAGE_NAME="$CUSTOM_REGISTRY"
fi

# Extract version from pyproject.toml
if [[ ! -f "pyproject.toml" ]]; then
    echo "Error: pyproject.toml not found"
    exit 1
fi

VERSION=$(grep '^version = ' pyproject.toml | cut -d'"' -f2)
if [[ -z "$VERSION" ]]; then
    echo "Error: Could not extract version from pyproject.toml"
    exit 1
fi

# Get git information
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CACHE_BUST=$(date +%s)

# Parse semantic version
IFS='.' read -r MAJOR MINOR PATCH <<< "${VERSION}"

# Handle pre-release versions (e.g., 2.0.0-beta.1)
if [[ "$PATCH" == *"-"* ]]; then
    PATCH_BASE=$(echo "$PATCH" | cut -d'-' -f1)
    PRERELEASE=$(echo "$PATCH" | cut -d'-' -f2)
    echo "Building KATO version ${VERSION} (pre-release: ${PRERELEASE}, commit: ${GIT_COMMIT})"
else
    PATCH_BASE="$PATCH"
    PRERELEASE=""
    echo "Building KATO version ${VERSION} (commit: ${GIT_COMMIT})"
fi

echo "Image name: ${IMAGE_NAME}"
echo "Build date: ${BUILD_DATE}"
echo "Git commit: ${GIT_COMMIT}"
echo ""

# Build tags array
TAGS=()
TAGS+=("-t" "${IMAGE_NAME}:${VERSION}")

# Only add rolling tags for non-pre-release versions
if [[ -z "$PRERELEASE" ]]; then
    TAGS+=("-t" "${IMAGE_NAME}:${MAJOR}.${MINOR}")
    TAGS+=("-t" "${IMAGE_NAME}:${MAJOR}")
    TAGS+=("-t" "${IMAGE_NAME}:latest")
    echo "Tags to be created:"
    echo "  - ${IMAGE_NAME}:${VERSION} (specific version)"
    echo "  - ${IMAGE_NAME}:${MAJOR}.${MINOR} (minor version)"
    echo "  - ${IMAGE_NAME}:${MAJOR} (major version)"
    echo "  - ${IMAGE_NAME}:latest (latest stable)"
else
    echo "Pre-release detected - only tagging with specific version:"
    echo "  - ${IMAGE_NAME}:${VERSION}"
fi

echo ""
echo "Building image..."

# Build image with metadata
docker build \
  --build-arg VERSION="${VERSION}" \
  --build-arg GIT_COMMIT="${GIT_COMMIT}" \
  --build-arg BUILD_DATE="${BUILD_DATE}" \
  --build-arg CACHE_BUST="${CACHE_BUST}" \
  "${TAGS[@]}" \
  .

echo ""
echo "Build completed successfully!"

# Push images if not disabled
if [[ "$NO_PUSH" == "false" ]]; then
    echo ""
    echo "Pushing images to registry..."

    # Push specific version tag
    echo "  Pushing ${IMAGE_NAME}:${VERSION}..."
    docker push "${IMAGE_NAME}:${VERSION}"

    # Push rolling tags for stable releases only
    if [[ -z "$PRERELEASE" ]]; then
        echo "  Pushing ${IMAGE_NAME}:${MAJOR}.${MINOR}..."
        docker push "${IMAGE_NAME}:${MAJOR}.${MINOR}"

        echo "  Pushing ${IMAGE_NAME}:${MAJOR}..."
        docker push "${IMAGE_NAME}:${MAJOR}"

        echo "  Pushing ${IMAGE_NAME}:latest..."
        docker push "${IMAGE_NAME}:latest"
    fi

    echo ""
    echo "Successfully pushed ${IMAGE_NAME}:${VERSION}"
    echo ""
    echo "You can pull this image with:"
    echo "  docker pull ${IMAGE_NAME}:${VERSION}"
    if [[ -z "$PRERELEASE" ]]; then
        echo "  docker pull ${IMAGE_NAME}:${MAJOR}.${MINOR}"
        echo "  docker pull ${IMAGE_NAME}:${MAJOR}"
        echo "  docker pull ${IMAGE_NAME}:latest"
    fi
else
    echo ""
    echo "Skipping push (--no-push flag set)"
    echo "To push manually, run:"
    echo "  docker push ${IMAGE_NAME}:${VERSION}"
    if [[ -z "$PRERELEASE" ]]; then
        echo "  docker push ${IMAGE_NAME}:${MAJOR}.${MINOR}"
        echo "  docker push ${IMAGE_NAME}:${MAJOR}"
        echo "  docker push ${IMAGE_NAME}:latest"
    fi
fi

echo ""
echo "Done!"
