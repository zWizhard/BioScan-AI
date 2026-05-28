"""Testes do cliente de visão (Tarefa 3).

Toda a I/O HTTP é mockada com httpx.MockTransport — nenhuma chamada real à
HuggingFace é feita. A imagem de entrada é um PNG 224×224 gerado via Pillow.
"""

import io

import httpx
import pytest
from PIL import Image

from app.services import vision
from app.services.vision import VisionServiceError, identify_species
from app.utils.image import ImageValidationError, preprocess_image


def _make_png(size: tuple[int, int] = (224, 224)) -> bytes:
    """Gera os bytes de um PNG sólido do tamanho indicado."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(120, 180, 75)).save(buffer, format="PNG")
    return buffer.getvalue()


# Resposta típica do modelo de classificação da HF: lista ordenável de label/score.
_FAKE_HF_RESPONSE = [
    {"label": f"Species {i}", "score": round(0.9 - i * 0.05, 4)} for i in range(15)
]


def _client_returning(payload: object, status_code: int = 200) -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_preprocess_resizes_to_224() -> None:
    processed = preprocess_image(_make_png((640, 480)))
    assert Image.open(io.BytesIO(processed)).size == (224, 224)


def test_preprocess_rejects_invalid_bytes() -> None:
    with pytest.raises(ImageValidationError):
        preprocess_image(b"isto nao e uma imagem")


@pytest.mark.asyncio
async def test_identify_species_returns_top_10_sorted() -> None:
    async with _client_returning(_FAKE_HF_RESPONSE) as client:
        results = await identify_species(_make_png(), client=client)

    assert len(results) == 10  # top-K limita a 10
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)  # ordenado por score desc
    assert results[0]["label"] == "Species 0"
    assert set(results[0]) == {"label", "score"}


@pytest.mark.asyncio
async def test_identify_species_retries_then_succeeds(monkeypatch) -> None:
    # Evita esperar os backoffs reais (2s/4s/8s) durante o teste.
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(vision.asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "Model is loading"})
        return httpx.Response(200, json=_FAKE_HF_RESPONSE)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await identify_species(_make_png(), client=client)

    assert calls["n"] == 3  # 2 falhas transitórias + 1 sucesso
    assert sleeps == [2.0, 4.0]  # backoff exponencial entre as tentativas
    assert len(results) == 10


@pytest.mark.asyncio
async def test_identify_species_raises_on_client_error() -> None:
    # 401 (chave inválida) é definitivo: não deve haver retry, levanta erro.
    async with _client_returning({"error": "invalid token"}, status_code=401) as client:
        with pytest.raises(VisionServiceError):
            await identify_species(_make_png(), client=client)
