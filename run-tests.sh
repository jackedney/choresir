#!/bin/bash
set -e

# Detect container runtime (prefer podman, fall back to docker)
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    COMPOSE_CMD="podman-compose"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
    COMPOSE_CMD="docker compose"
else
    echo "Error: Neither podman nor docker found in PATH"
    exit 1
fi

echo "Using container runtime: $CONTAINER_CMD"

# Build and run tests
$COMPOSE_CMD -f compose.test.yml build
$COMPOSE_CMD -f compose.test.yml run --rm test "$@"
