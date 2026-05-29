"""Schemas Pydantic de entrada da API."""

from typing import Literal

from pydantic import BaseModel, Field

# Perfis de exposição do usuário (reservado para ajuste de conduta por contexto).
UserContext = Literal["rural_worker", "hiker", "urban", "professional"]


class IdentifyRequest(BaseModel):
    """Payload do POST /api/v1/identify."""

    image_base64: str = Field(..., description="Imagem em base64 (até ~5MB).")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    user_context: UserContext | None = None
