"""Cliente da HuggingFace Inference API (modelo de visão).

Envia a imagem pré-processada ao ViT-Large/iNat21 e devolve as espécies
candidatas com seus scores (verossimilhança P(imagem | espécie) do motor
bayesiano). Erros transitórios — modelo "carregando" (503) ou falhas 5xx/rede —
são tratados com backoff exponencial. A falha persistente levanta
`VisionServiceError`, que o orquestrador do /identify converte em modo degradado.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.utils.image import preprocess_image

logger = logging.getLogger("bioscan.vision")
settings = get_settings()

# Modelo primário: ViT-Large treinado no iNaturalist 2021 (10k espécies).
PRIMARY_MODEL = "Smithsonian/vit-large-patch16-224-iNat21"
HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"

TOP_K = 10
# Backoff exponencial entre tentativas: aguarda 2s, depois 4s, depois 8s.
RETRY_BACKOFFS: tuple[float, ...] = (2.0, 4.0, 8.0)
REQUEST_TIMEOUT = 30.0


class VisionServiceError(RuntimeError):
    """Falha persistente ao consultar o serviço de inferência de imagem."""


def _is_transient(status_code: int) -> bool:
    """503 = modelo aquecendo na HF; 5xx = falha temporária do servidor."""
    return status_code == 503 or 500 <= status_code < 600


async def _post_with_retry(
    client: httpx.AsyncClient, url: str, content: bytes, headers: dict[str, str]
) -> Any:
    """POST com retry e backoff exponencial em erros transitórios.

    Faz 1 tentativa inicial + 1 retry por backoff em RETRY_BACKOFFS (4 no total).
    Erros 4xx (ex.: chave inválida) não são retentados — falham imediatamente.
    """
    last_error: Exception | None = None

    for attempt in range(len(RETRY_BACKOFFS) + 1):
        try:
            response = await client.post(url, content=content, headers=headers)

            if _is_transient(response.status_code):
                raise httpx.HTTPStatusError(
                    f"Status transitório {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response.json()

        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            # 4xx (exceto 503) é erro definitivo do cliente — não adianta retentar.
            if (
                isinstance(exc, httpx.HTTPStatusError)
                and not _is_transient(exc.response.status_code)
            ):
                raise VisionServiceError(
                    f"Erro {exc.response.status_code} da HuggingFace Inference API."
                ) from exc

            last_error = exc
            if attempt < len(RETRY_BACKOFFS):
                backoff = RETRY_BACKOFFS[attempt]
                logger.warning(
                    "Tentativa %d/%d falhou (%s). Novo retry em %.0fs.",
                    attempt + 1,
                    len(RETRY_BACKOFFS) + 1,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

    raise VisionServiceError(
        "Serviço de visão indisponível após múltiplas tentativas."
    ) from last_error


def _parse_top_k(payload: Any, top_k: int) -> list[dict]:
    """Normaliza a resposta da HF para [{'label': str, 'score': float}, ...] top-K."""
    if not isinstance(payload, list):
        raise VisionServiceError(
            f"Resposta inesperada da HuggingFace Inference API: {type(payload)!r}."
        )

    candidates = [
        {"label": item["label"], "score": float(item["score"])}
        for item in payload
        if isinstance(item, dict) and "label" in item and "score" in item
    ]
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:top_k]


async def identify_species(
    image_bytes: bytes,
    *,
    client: httpx.AsyncClient | None = None,
    model: str = PRIMARY_MODEL,
    top_k: int = TOP_K,
) -> list[dict]:
    """Identifica espécies candidatas a partir dos bytes de uma imagem.

    Redimensiona para 224×224, envia ao endpoint do ViT e retorna o top-K de
    candidatas ordenado por score decrescente. `client` pode ser injetado nos
    testes (ex.: httpx.MockTransport); caso contrário, um é criado e fechado aqui.
    """
    processed = preprocess_image(image_bytes)
    url = f"{HF_INFERENCE_BASE}/{model}"
    headers = {"Authorization": f"Bearer {settings.hf_api_key}"}

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    try:
        payload = await _post_with_retry(client, url, processed, headers)
    finally:
        if owns_client:
            await client.aclose()

    results = _parse_top_k(payload, top_k)
    logger.info("Visão retornou %d candidata(s). Topo: %s", len(results), results[:1])
    return results
