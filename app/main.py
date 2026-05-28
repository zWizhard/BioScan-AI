"""Aplicação FastAPI do BioScan AI e roteamento principal.

Tarefa 2 cobre o bootstrap do app, a criação do schema no startup e a rota de
detalhe de espécie. O endpoint `/identify` e o `/health` completo chegam na
Tarefa 6.
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_session, init_db
from app.models.response import SpeciesDetail
from app.services.risk import get_species_by_name

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("bioscan")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Garante que o schema do banco exista antes de servir requests."""
    await init_db()
    logger.info("BioScan AI iniciado (env=%s).", settings.app_env)
    yield


app = FastAPI(
    title="BioScan AI",
    version="0.1.0-dev",
    description="Identificação probabilística de animais focada em risco.",
    lifespan=lifespan,
)

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Health check básico do serviço (dependências externas chegam na Tarefa 6)."""
    return {"status": "ok", "version": app.version}


@api_router.get("/species/{scientific_name}", response_model=SpeciesDetail, tags=["species"])
async def get_species(
    scientific_name: str = Path(..., description="Nome científico, ex: Bothrops jararaca"),
    session: AsyncSession = Depends(get_session),
) -> SpeciesDetail:
    """Retorna os dados completos de uma espécie no banco de risco."""
    species = await get_species_by_name(session, scientific_name)
    if species is None:
        raise HTTPException(
            status_code=404,
            detail=f"Espécie '{scientific_name}' não encontrada no banco de risco.",
        )
    return SpeciesDetail.model_validate(species)


app.include_router(api_router)
