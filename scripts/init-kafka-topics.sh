#!/usr/bin/env bash
set -euo pipefail

echo "Creating ReWearIt Kafka topics in Redpanda..."

docker exec rewearit-redpanda rpk topic create \
  rewearit.items.events -p 3 \
  rewearit.ai.events -p 3 \
  rewearit.orders.events -p 3 \
  rewearit.pricing.events -p 3 \
  rewearit.analytics.pricing_metrics -p 3 -c cleanup.policy=compact \
  rewearit.security.alerts -p 3 \
  rewearit.telemetry.events -p 6 \
  rewearit.dead_letter.queue -p 3 || true

echo "Kafka topics created successfully:"
docker exec rewearit-redpanda rpk topic list
