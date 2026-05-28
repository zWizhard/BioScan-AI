"""Seed idempotente do banco de risco.

Lê `data/species_risk_seed.json` e insere as espécies em `species_risk`.
Rodar duas vezes não cria duplicatas (regra #6): usamos o INSERT ... ON CONFLICT
DO NOTHING do SQLite sobre a constraint UNIQUE de `scientific_name`.

Pode ser executado como script standalone:  python -m app.db.seed
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.database import engine, init_db
from app.db.models import SpeciesRisk

logger = logging.getLogger(__name__)

# data/species_risk_seed.json — relativo à raiz do projeto (dois níveis acima daqui).
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "species_risk_seed.json"

# Apenas colunas reais do modelo entram no INSERT; chaves extras no JSON são
# ignoradas para o seed não quebrar quando o schema do arquivo evoluir.
_VALID_COLUMNS = {c.name for c in SpeciesRisk.__table__.columns}


def load_seed_records(path: Path = SEED_PATH) -> list[dict[str, Any]]:
    """Carrega e normaliza os registros do arquivo de seed."""
    with path.open(encoding="utf-8") as fh:
        raw: list[dict[str, Any]] = json.load(fh)

    records: list[dict[str, Any]] = []
    for entry in raw:
        # `class` é palavra reservada em Python; no modelo o atributo é `class_`.
        normalized = {("class_" if k == "class" else k): v for k, v in entry.items()}
        records.append({k: v for k, v in normalized.items() if k in _VALID_COLUMNS})
    return records


async def seed_database(path: Path = SEED_PATH) -> int:
    """Insere as espécies do seed. Retorna quantos registros foram efetivamente inseridos."""
    await init_db()
    records = load_seed_records(path)
    if not records:
        logger.warning("Seed vazio: nenhum registro encontrado em %s", path)
        return 0

    inserted = 0
    async with engine.begin() as conn:
        for record in records:
            stmt = (
                sqlite_insert(SpeciesRisk)
                .values(**record)
                .on_conflict_do_nothing(index_elements=["scientific_name"])
            )
            result = await conn.execute(stmt)
            inserted += result.rowcount or 0

    logger.info(
        "Seed concluído: %d novo(s) registro(s) inserido(s) de %d no arquivo.",
        inserted,
        len(records),
    )
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = asyncio.run(seed_database())
    print(f"Seed concluído: {count} novo(s) registro(s) inserido(s).")
