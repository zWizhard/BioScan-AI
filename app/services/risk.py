"""Consulta ao banco curado de risco.

Camada fina entre a API e o ORM: isola as queries do banco de risco para que os
endpoints (e, futuramente, o orquestrador do `/identify`) não conheçam detalhes
do SQLAlchemy.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SpeciesRisk

# Severidade relativa dos níveis de risco (maior = mais grave). Usado para
# definir o risco geral da resposta e para comparar candidatas.
RISK_SEVERITY: dict[str, int] = {
    "CRÍTICO": 4,
    "ALTO": 3,
    "MÉDIO": 2,
    "BAIXO": 1,
    "NENHUM": 0,
}


def risk_severity(level: str | None) -> int:
    """Ordinal de severidade do nível de risco (desconhecido = 0)."""
    return RISK_SEVERITY.get((level or "").upper(), 0)


def build_immediate_action(
    risk_level: str | None,
    safe_distance_m: int | None,
    emergency_contact: str | None,
) -> str:
    """Monta a frase de conduta imediata a partir do risco da espécie no topo.

    O texto é curto e acionável (foco do produto): o usuário em campo precisa
    saber em uma frase o que fazer agora.
    """
    level = (risk_level or "").upper()
    distance = f"Mantenha distância mínima de {safe_distance_m}m. " if safe_distance_m else ""
    contact = f"Contato: {emergency_contact}." if emergency_contact else ""

    if level == "CRÍTICO":
        return f"AFASTE-SE IMEDIATAMENTE. {distance}{contact}".strip()
    if level == "ALTO":
        return f"Evite contato e mantenha-se a distância segura. {distance}{contact}".strip()
    if level == "MÉDIO":
        return f"Tenha cautela e evite aproximação. {distance}{contact}".strip()
    if level == "BAIXO":
        return "Risco baixo. Observe à distância e evite manuseio.".strip()
    return "Sem risco conhecido para esta identificação. Mantenha bom senso em campo."


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
