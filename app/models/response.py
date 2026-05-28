"""Schemas Pydantic de saída da API.

Estes modelos definem o contrato público da API e desacoplam a serialização das
respostas dos modelos ORM internos. Por ora cobrem o detalhe de espécie
(Tarefa 2); os schemas do `/identify` chegam na Tarefa 6.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
