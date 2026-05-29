"""Schemas Pydantic de saída da API.

Estes modelos definem o contrato público da API e desacoplam a serialização das
respostas dos modelos ORM internos: o detalhe de espécie (Tarefa 2) e a resposta
do /identify (Tarefa 6).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpeciesDetail(BaseModel):
    """Representação completa de uma espécie no banco de risco."""

    # from_attributes permite construir o schema direto do objeto ORM.
    model_config = ConfigDict(from_attributes=True)

    scientific_name: str
    common_name_pt: str | None = None
    common_name_en: str | None = None

    kingdom: str | None = None
    class_: str | None = None
    order_name: str | None = None
    family: str | None = None

    risk_level: str
    risk_category: str | None = None
    venom_type: str | None = None

    is_protected: bool = False
    cites_appendix: str | None = None
    brazil_endemic: bool = False

    safe_distance_m: int | None = None
    first_aid: str | None = None
    what_not_to_do: str | None = None
    emergency_contact: str | None = None

    description: str | None = None
    habitat: str | None = None
    behavior_notes: str | None = None

    inat_taxon_id: int | None = None
    gbif_taxon_key: int | None = None
    image_url: str | None = None
    sources: str | None = None

    updated_at: datetime | None = None


class RiskInfo(BaseModel):
    """Bloco de risco anexado a cada candidata do /identify."""

    level: str
    category: str | None = None
    venom_type: str | None = None
    safe_distance_m: int | None = None
    first_aid: str | None = None
    what_not_to_do: str | None = None
    emergency_contact: str | None = None


class Candidate(BaseModel):
    """Uma espécie candidata no ranking do /identify."""

    # `model_confidence` não é um namespace protegido do Pydantic aqui.
    model_config = ConfigDict(protected_namespaces=())

    rank: int
    scientific_name: str
    common_name_pt: str | None = None
    probability: float
    model_confidence: float
    # null quando a GBIF está indisponível (modo degradado).
    geographic_prior: float | None = None
    # null quando a espécie não consta no banco curado de risco.
    risk: RiskInfo | None = None


class GeographicContext(BaseModel):
    """Contexto geográfico da consulta."""

    region: str | None = None
    radius_km: int
    occurrences_found: int | None = None


class IdentifyResponse(BaseModel):
    """Resposta do POST /api/v1/identify."""

    # `model_version` não é um namespace protegido do Pydantic aqui.
    model_config = ConfigDict(protected_namespaces=())

    request_id: str
    processed_at: datetime
    top_candidates: list[Candidate]
    overall_risk_level: str
    immediate_action: str
    disclaimer: str = Field(
        default="Identificação probabilística. Não substitui avaliação profissional."
    )
    model_version: str
    geographic_context: GeographicContext
    # true quando alguma dependência externa falhou e a resposta foi degradada.
    degraded_mode: bool = False
