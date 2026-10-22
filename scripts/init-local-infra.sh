#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/deploy/docker-compose/docker-compose.yml"

echo "=========================================="
echo " Starting ReWearIt Local Infrastructure"
echo "=========================================="

docker compose -f "${COMPOSE_FILE}" up -d

echo "Waiting for Redpanda to become healthy..."
until docker exec rewearit-redpanda rpk cluster health | grep -iE 'healthy:.*true' > /dev/null 2>&1; do
  sleep 1
done

echo "Waiting for MinIO to become healthy..."
until docker exec rewearit-minio mc ready local > /dev/null 2>&1; do
  sleep 1
done

echo "Creating Kafka topics..."
docker exec rewearit-redpanda rpk topic create \
  rewearit.items.events -p 3 \
  rewearit.ai.events -p 3 \
  rewearit.orders.events -p 3 \
  rewearit.pricing.events -p 3 \
  rewearit.analytics.pricing_metrics -p 3 -c cleanup.policy=compact \
  rewearit.security.alerts -p 3 \
  rewearit.telemetry.events -p 6 \
  rewearit.dead_letter.queue -p 3 || true

echo "Setting up MinIO storage buckets..."
docker exec rewearit-minio mc alias set local http://localhost:9000 minioadmin minioadminpassword > /dev/null 2>&1 || true
docker exec rewearit-minio mc mb --ignore-existing local/rewearit-garments > /dev/null 2>&1 || true
docker exec rewearit-minio mc mb --ignore-existing local/rewearit-lakehouse > /dev/null 2>&1 || true

echo "=========================================="
echo " Infrastructure is ready!"
echo " - Redpanda Kafka:  localhost:9092"
echo " - Redpanda UI:     http://localhost:8080"
echo " - MinIO S3 API:    http://localhost:9000"
echo " - MinIO Console:   http://localhost:9001 (minioadmin / minioadminpassword)"
echo " - Postgres Catalog (pgvector): localhost:5432 (catalog_user / catalog_password)"
echo " - Postgres Orders:             localhost:5433 (orders_user / orders_password)"
echo " - Postgres Pricing:            localhost:5434 (pricing_user / pricing_password)"
echo " - Redis Cache & Locks:         localhost:6379"
echo "=========================================="
