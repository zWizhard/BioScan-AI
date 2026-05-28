"""Consulta ao banco curado de risco.

Camada fina entre a API e o ORM: isola as queries do banco de risco para que os
endpoints (e, futuramente, o orquestrador do `/identify`) não conheçam detalhes
do SQLAlchemy.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SpeciesRisk


async def get_species_by_name(
    session: AsyncSession, scientific_name: str
) -> SpeciesRisk | None:
    """Retorna a espécie pelo nome científico, ou None se não estiver no banco.

    A busca é case-insensitive: o output do modelo de visão e a digitação do
    usuário nem sempre respeitam a capitalização do nome científico.
    """
    stmt = select(SpeciesRisk).where(
        SpeciesRisk.scientific_name.ilike(scientific_name.strip())
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
