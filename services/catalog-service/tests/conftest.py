"""Test fixtures and connection guards for catalog service."""
import socket
import pytest


def is_service_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


requires_postgres = pytest.mark.skipif(
    not is_service_reachable("127.0.0.1", 5432),
    reason="Live PostgreSQL 16 on port 5432 is not reachable",
)
