#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Compiling Protobuf schemas to Python stubs..."

docker run --rm \
  -v "${PROJECT_ROOT}:/workspace" \
  -w /workspace \
  python:3.12-slim \
  bash -c "pip install --quiet grpcio-tools && \
           mkdir -p gen/python/rewearit_schemas && \
           touch gen/python/rewearit_schemas/__init__.py && \
           python -m grpc_tools.protoc -I docs/schemas \
             --python_out=gen/python/rewearit_schemas \
             --grpc_python_out=gen/python/rewearit_schemas \
             docs/schemas/events.proto docs/schemas/catalog_service.proto && \
           chown -R $(id -u):$(id -g) /workspace/gen"

echo "Protobuf Python stubs generated in gen/python/rewearit_schemas/:"
ls -lh "${PROJECT_ROOT}/gen/python/rewearit_schemas"
