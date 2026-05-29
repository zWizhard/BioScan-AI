"""Testes do banco de risco populado pelo seed (métrica de MVP: ≥50 espécies)."""

import pytest
from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.db.models import SpeciesRisk

VALID_RISK_LEVELS = {"CRÍTICO", "ALTO", "MÉDIO", "BAIXO", "NENHUM"}


@pytest.mark.asyncio
async def test_seed_has_at_least_50_species() -> None:
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(SpeciesRisk))
    assert total is not None and total >= 50


@pytest.mark.asyncio
async def test_all_risk_levels_are_valid() -> None:
    async with SessionLocal() as session:
        levels = (await session.execute(select(SpeciesRisk.risk_level))).scalars().all()
    assert set(levels) <= VALID_RISK_LEVELS


@pytest.mark.asyncio
async def test_venomous_species_have_first_aid() -> None:
    # Numa app de risco, toda espécie com veneno precisa ter conduta de socorro.
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(SpeciesRisk).where(SpeciesRisk.risk_category == "VENENO")
            )
        ).scalars().all()
    assert rows, "esperado ao menos uma espécie peçonhenta no seed"
    for species in rows:
        assert species.first_aid, f"{species.scientific_name} sem first_aid"
        assert species.emergency_contact, f"{species.scientific_name} sem contato"
