"""Fixtures compartilhadas dos testes."""

import asyncio

import pytest

from app.db.seed import seed_database


@pytest.fixture(scope="session", autouse=True)
def _seed_db() -> None:
    """Garante schema criado e seed aplicado antes da suíte (idempotente)."""
    asyncio.run(seed_database())
