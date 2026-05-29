"""Aplicação FastAPI do BioScan AI e roteamento principal.

Orquestra o fluxo do produto: visão computacional → inferência bayesiana →
enriquecimento com o banco curado de risco. Segue a regra #2 (nunca quebrar a
API): falhas de dependências externas degradam a resposta em vez de retornar 500.
"""

import base64
import binascii
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_session, init_db
from app.models.request import IdentifyRequest
from app.models.response import (
    Candidate,
    GeographicContext,
    IdentifyResponse,
    RiskInfo,
    SpeciesDetail,
)
from app.services import gbif
from app.services.bayesian import bayesian_inference
from app.services.gbif import GbifServiceError
from app.services.risk import build_immediate_action, get_species_by_name, risk_severity
from app.services.vision import PRIMARY_MODEL, identify_species

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("bioscan")

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # limite de 5MB do payload de imagem
TOP_CANDIDATES = 5  # nº de candidatas expostas na resposta


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _decode_image(image_base64: str) -> bytes:
    """Decodifica o base64 (tolerando prefixo data URI) e valida o tamanho."""
    payload = image_base64.split(",", 1)[1] if image_base64.startswith("data:") else image_base64
    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="image_base64 inválido.") from exc

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Imagem vazia.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Imagem excede o limite de 5MB.")
    return image_bytes


def _normalize_scores(model_scores: list[dict]) -> list[dict]:
    """Fallback sem GBIF: probabilidade = score do modelo renormalizado p/ somar 1."""
    total = sum(s["score"] for s in model_scores) or 1.0
    return [
        {
            "species": s["label"],
            "probability": s["score"] / total,
            "model_confidence": s["score"],
            "geographic_prior": None,
        }
        for s in model_scores
    ]


async def _build_candidates(
    ranked: list[dict], session: AsyncSession
) -> list[Candidate]:
    """Enriquece o ranking com dados do banco de risco e monta as candidatas."""
    candidates: list[Candidate] = []
    for rank, item in enumerate(ranked[:TOP_CANDIDATES], start=1):
        species_row = await get_species_by_name(session, item["species"])
        risk = None
        common_name = None
        if species_row is not None:
            common_name = species_row.common_name_pt
            risk = RiskInfo(
                level=species_row.risk_level,
                category=species_row.risk_category,
                venom_type=species_row.venom_type,
                safe_distance_m=species_row.safe_distance_m,
                first_aid=species_row.first_aid,
                what_not_to_do=species_row.what_not_to_do,
                emergency_contact=species_row.emergency_contact,
            )
        candidates.append(
            Candidate(
                rank=rank,
                scientific_name=item["species"],
                common_name_pt=common_name,
                probability=round(item["probability"], 4),
                model_confidence=round(item["model_confidence"], 4),
                geographic_prior=(
                    round(item["geographic_prior"], 4)
                    if item["geographic_prior"] is not None
                    else None
                ),
                risk=risk,
            )
        )
    return candidates


def _overall_risk(candidates: list[Candidate]) -> Candidate | None:
    """Candidata que dita o risco geral: a mais grave (desempate por probabilidade).

    Decisão de segurança: num produto de risco, a conduta deve refletir a espécie
    *mais perigosa plausível* no ranking, não apenas a #1 por probabilidade.
    """
    with_risk = [c for c in candidates if c.risk is not None]
    if not with_risk:
        return None
    return max(with_risk, key=lambda c: (risk_severity(c.risk.level), c.probability))


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

async def check_gbif() -> str:
    """Reachability rápida da GBIF (best-effort, nunca levanta)."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(gbif.GBIF_BASE_URL)
        return "ok" if resp.status_code < 500 else "unavailable"
    except httpx.HTTPError:
        return "unavailable"


async def check_huggingface() -> str:
    """Status da HuggingFace: configurada e alcançável (best-effort)."""
    if not settings.hf_api_key or settings.hf_api_key.startswith("hf_xxxx"):
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://huggingface.co/api/whoami-v2",
                                    headers={"Authorization": f"Bearer {settings.hf_api_key}"})
        return "ok" if resp.status_code < 500 else "unavailable"
    except httpx.HTTPError:
        return "unavailable"


@api_router.get("/health", tags=["meta"])
async def health(session: AsyncSession = Depends(get_session)) -> dict:
    """Health check do serviço e das dependências externas."""
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 — health nunca deve levantar
        database = "error"

    hf_status = await check_huggingface()
    gbif_status = await check_gbif()

    overall = "ok" if database == "ok" else "degraded"
    return {
        "status": overall,
        "version": app.version,
        "dependencies": {
            "database": database,
            "huggingface": hf_status,
            "gbif": gbif_status,
        },
    }


# --------------------------------------------------------------------------- #
# Endpoints de domínio
# --------------------------------------------------------------------------- #

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


@api_router.post("/identify", response_model=IdentifyResponse, tags=["identify"])
async def identify(
    payload: IdentifyRequest,
    session: AsyncSession = Depends(get_session),
) -> IdentifyResponse:
    """Identifica a espécie e avalia o risco a partir de imagem + GPS.

    Fluxo: visão (HuggingFace) → bayesiano (GBIF) → banco de risco. Falhas das
    dependências externas degradam a resposta (degraded_mode=true), sem 500.
    """
    request_id = str(uuid.uuid4())
    processed_at = datetime.now(timezone.utc)
    month = processed_at.month
    started = time.perf_counter()

    image_bytes = _decode_image(payload.image_base64)
    degraded = False

    # 1) Visão computacional — núcleo da identificação.
    try:
        model_scores = await identify_species(image_bytes)
    except Exception as exc:  # noqa: BLE001 — qualquer falha de visão degrada, não 500
        # Sem visão não há identificação: resposta degradada vazia (não 500).
        logger.error("Falha no serviço de visão: %s", exc)
        return IdentifyResponse(
            request_id=request_id,
            processed_at=processed_at,
            top_candidates=[],
            overall_risk_level="NENHUM",
            immediate_action="Não foi possível identificar a espécie no momento. Tente novamente.",
            model_version=PRIMARY_MODEL,
            geographic_context=GeographicContext(
                region=None, radius_km=settings.gbif_search_radius_km, occurrences_found=None
            ),
            degraded_mode=True,
        )

    # Descarta candidatas abaixo do limiar de confiança (ruído do modelo).
    filtered = [s for s in model_scores if s["score"] >= settings.min_model_confidence]
    if not filtered:
        filtered = model_scores[:1]  # nunca devolve vazio se o modelo respondeu

    # 2) Inferência bayesiana (GBIF). Falha → ranking só pelo modelo (prior=null).
    try:
        ranked = await bayesian_inference(filtered, payload.latitude, payload.longitude, month)
    except GbifServiceError as exc:
        logger.warning("GBIF indisponível; degradando para ranking só do modelo: %s", exc)
        ranked = sorted(_normalize_scores(filtered), key=lambda x: x["probability"], reverse=True)
        degraded = True

    # 3) Enriquecimento com o banco de risco.
    candidates = await _build_candidates(ranked, session)
    driver = _overall_risk(candidates)

    if driver is not None and driver.risk is not None:
        overall_level = driver.risk.level
        immediate_action = build_immediate_action(
            driver.risk.level, driver.risk.safe_distance_m, driver.risk.emergency_contact
        )
    else:
        overall_level = "NENHUM"
        immediate_action = build_immediate_action(None, None, None)

    latency_ms = round((time.perf_counter() - started) * 1000)
    logger.info(
        "identify request_id=%s lat=%.4f lng=%.4f top_species=%s risk_level=%s "
        "degraded=%s latency_ms=%d",
        request_id,
        payload.latitude,
        payload.longitude,
        candidates[0].scientific_name if candidates else None,
        overall_level,
        degraded,
        latency_ms,
    )

    return IdentifyResponse(
        request_id=request_id,
        processed_at=processed_at,
        top_candidates=candidates,
        overall_risk_level=overall_level,
        immediate_action=immediate_action,
        model_version=PRIMARY_MODEL,
        geographic_context=GeographicContext(
            region=None,
            radius_km=settings.gbif_search_radius_km,
            occurrences_found=None,
        ),
        degraded_mode=degraded,
    )


app.include_router(api_router)
