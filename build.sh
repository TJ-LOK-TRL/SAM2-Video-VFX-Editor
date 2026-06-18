#!/bin/bash
set -e

cd "$(dirname "$0")"

NAMESPACE="sam2"
IMAGE_PREFIX="ghcr.io/tj-lok-trl/sam2-video-vfx-editor"
REGISTRY="ghcr.io"

# Detect if running in k3s or regular Docker/Kubernetes
if command -v k3s &> /dev/null; then
    if [ "$EUID" -eq 0 ]; then
        KUBECTL="k3s kubectl"
    else
        KUBECTL="sudo k3s kubectl"
    fi
else
    KUBECTL="kubectl"
fi

# Default services if none specified
SERVICES=("$@")

if [ ${#SERVICES[@]} -eq 0 ]; then
    SERVICES=(backend worker frontend cloudflared)
fi

if [ "${SERVICES[0]}" = "all" ]; then
    SERVICES=(backend frontend cloudflared worker sam2-job)
fi

# Validate service names
VALID_SERVICES=(backend frontend cloudflared worker sam2-job)
for svc in "${SERVICES[@]}"; do
    if [[ ! " ${VALID_SERVICES[@]} " =~ " ${svc} " ]]; then
        echo "ERROR: Unknown service '$svc'"
        echo "Valid services: ${VALID_SERVICES[@]}"
        exit 1
    fi
done

echo "====================================="
echo "SAM2 Video VFX Editor - Build & Deploy"
echo "====================================="
echo "Services to build: ${SERVICES[@]}"
echo "Image registry: $IMAGE_PREFIX"
echo "Kubernetes namespace: $NAMESPACE"
echo "====================================="
echo

# Check Docker daemon
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker daemon is not running"
    exit 1
fi

# Build and push images
for svc in "${SERVICES[@]}"; do
    echo ">>> Building $svc..."
    
    # Special handling for different services
    if [ "$svc" = "worker" ]; then
        # Worker uses same image as backend
        echo "Skipping build for worker (uses backend image)"
        continue
    elif [ "$svc" = "sam2-job" ]; then
        # Sam2-job requires special Docker setup (GPU base image)
        if [ ! -f "./$svc/Dockerfile" ]; then
            echo "WARNING: Dockerfile for ./$svc not found, skipping build"
            continue
        fi
    fi

    if [ ! -f "./$svc/Dockerfile" ]; then
        echo "ERROR: Dockerfile not found at ./$svc/Dockerfile"
        exit 1
    fi
    
    # Use service directory as build context for cloudflared (entrypoint.sh is there)
    if [ "$svc" = "cloudflared" ]; then
        BUILD_CONTEXT="./$svc"
    else
        BUILD_CONTEXT="."
    fi

    docker build \
        -f ./$svc/Dockerfile \
        -t ${IMAGE_PREFIX}/${svc}:latest \
        $BUILD_CONTEXT
    
    echo ">>> Pushing $svc to $REGISTRY..."
    docker push ${IMAGE_PREFIX}/${svc}:latest
    echo
done

echo "====================================="
echo "Restarting deployments"
echo "====================================="
echo

RESTART_TARGETS=()

for svc in "${SERVICES[@]}"; do
    case "$svc" in
        sam2-job)
            # sam2-job is a one-off Kubernetes Job, not a long-running Deployment
            echo "Skipping rollout for $svc"
            ;;
        *)
            RESTART_TARGETS+=("deployment/${svc}")
            ;;
    esac
done

if [ ${#RESTART_TARGETS[@]} -gt 0 ]; then
    ${KUBECTL} rollout restart \
        "${RESTART_TARGETS[@]}" \
        -n ${NAMESPACE} || echo "WARNING: Some deployments may not exist yet"
else
    echo "No deployments to restart"
fi

echo
echo "====================================="
echo "Deployment status"
echo "====================================="
echo

${KUBECTL} get pods -n ${NAMESPACE} -o wide || true

echo
echo "====================================="
echo "Build and deploy completed!"
echo "====================================="
echo
echo "Usage examples:"
echo "  ./build.sh                    # Build: backend, frontend, cloudflared"
echo "  ./build.sh all                # Build all services"
echo "  ./build.sh backend frontend   # Build specific services"
echo