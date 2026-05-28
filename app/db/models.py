"""Modelos ORM (SQLAlchemy 2.0) do BioScan AI.

Por enquanto o domínio é o banco curado de risco por espécie. O modelo espelha
fielmente o schema definido no documento de produto — incluindo campos que ainda
não são preenchidos pelo seed inicial, mas que serão usados pelo enriquecimento
via GBIF/iNaturalist em tarefas posteriores.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa compartilhada por todos os modelos ORM."""


class SpeciesRisk(Base):
    """Banco curado de risco por espécie (tabela `species_risk`)."""

    __tablename__ = "species_risk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # `scientific_name` é a chave natural usada por toda a aplicação (output do
    # modelo de visão, lookups da API). UNIQUE garante a idempotência do seed.
    scientific_name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    common_name_pt: Mapped[str | None] = mapped_column(String)
    common_name_en: Mapped[str | None] = mapped_column(String)

    # Taxonomia (preenchida pelo enriquecimento GBIF/iNat em tarefas futuras).
    kingdom: Mapped[str | None] = mapped_column(String)
    class_: Mapped[str | None] = mapped_column("class", String)
    order_name: Mapped[str | None] = mapped_column(String)
    family: Mapped[str | None] = mapped_column(String)

    # Avaliação de risco — o coração do produto.
    risk_level: Mapped[str] = mapped_column(String, nullable=False)  # CRÍTICO..NENHUM
    risk_category: Mapped[str | None] = mapped_column(String)  # VENENO|ZOONOSE|ATAQUE|ALERGIA|NENHUM
    venom_type: Mapped[str | None] = mapped_column(String)  # HEMOTÓXICO|NEUROTÓXICO|CITOTÓXICO|NULL

    is_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    cites_appendix: Mapped[str | None] = mapped_column(String)  # I|II|III|NULL
    brazil_endemic: Mapped[bool] = mapped_column(Boolean, default=False)

    safe_distance_m: Mapped[int | None] = mapped_column(Integer)
    first_aid: Mapped[str | None] = mapped_column(Text)
    what_not_to_do: Mapped[str | None] = mapped_column(Text)
    emergency_contact: Mapped[str | None] = mapped_column(Text)

    description: Mapped[str | None] = mapped_column(Text)
    habitat: Mapped[str | None] = mapped_column(Text)
    behavior_notes: Mapped[str | None] = mapped_column(Text)

    # Chaves externas para enriquecimento de dados.
    inat_taxon_id: Mapped[int | None] = mapped_column(Integer)
    gbif_taxon_key: Mapped[int | None] = mapped_column(Integer)

    image_url: Mapped[str | None] = mapped_column(String)
    sources: Mapped[str | None] = mapped_column(Text)  # JSON array serializado

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
