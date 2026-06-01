"""Teste de integração do endpoint /identify e do /health (Tarefa 6).

Visão e GBIF são mockados — nenhuma chamada externa real. O banco usa o seed
(garantido pela fixture de sessão em conftest.py).
"""

import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.main import app
from app.services import bayesian

client = TestClient(app)


def _b64_png(size: tuple[int, int] = (224, 224)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(90, 150, 60)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


# Top-2 do "modelo": uma espécie crítica do seed e uma fora do banco de risco.
_FAKE_MODEL_SCORES = [
    {"label": "Bothrops jararaca", "score": 0.72},
    {"label": "Passer domesticus", "score": 0.18},
    {"label": "Ruido improvavel", "score": 0.01},  # abaixo do MIN_MODEL_CONFIDENCE
]


@pytest.fixture
def patch_pipeline(monkeypatch):
    """Mocka visão e contagem GBIF para um pipeline determinístico."""

    async def fake_identify_species(image_bytes):
        return list(_FAKE_MODEL_SCORES)

    counts = {"Bothrops jararaca": 800, "Passer domesticus": 50}

    async def fake_count(scientific_name, lat, lng, month, radius_km=None, *, client=None):
        return counts.get(scientific_name, 0)

    monkeypatch.setattr(main, "identify_species", fake_identify_species)
    monkeypatch.setattr(bayesian.gbif, "get_occurrence_count", fake_count)


def test_identify_full_pipeline(patch_pipeline) -> None:
    response = client.post(
        "/api/v1/identify",
        json={"image_base64": _b64_png(), "latitude": -23.5505, "longitude": -46.6333},
    )
    assert response.status_code == 200
    body = response.json()

    # Estrutura do contrato.
    assert body["request_id"]
    assert body["model_version"]  # reflete o modelo configurado em settings.hf_model
    assert body["degraded_mode"] is False
    assert body["geographic_context"]["radius_km"] == 50

    # A candidata de ruído (score 0.01) foi descartada pelo MIN_MODEL_CONFIDENCE.
    names = [c["scientific_name"] for c in body["top_candidates"]]
    assert "Ruido improvavel" not in names

    # Probabilidades posteriores somam ~1.0 e estão ordenadas.
    probs = [c["probability"] for c in body["top_candidates"]]
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) == pytest.approx(1.0, abs=1e-3)

    # A jararaca (no seed) traz o bloco de risco e dita o risco geral CRÍTICO.
    top = body["top_candidates"][0]
    assert top["scientific_name"] == "Bothrops jararaca"
    assert top["risk"]["level"] == "CRÍTICO"
    assert top["geographic_prior"] is not None
    assert body["overall_risk_level"] == "CRÍTICO"
    assert "AFASTE-SE" in body["immediate_action"]


def test_identify_degraded_when_gbif_fails(patch_pipeline, monkeypatch) -> None:
    # GBIF falha → ranking só pelo modelo, geographic_prior nulo, degraded_mode true.
    from app.services.gbif import GbifServiceError

    async def failing_count(*args, **kwargs):
        raise GbifServiceError("indisponível")

    monkeypatch.setattr(bayesian.gbif, "get_occurrence_count", failing_count)

    response = client.post(
        "/api/v1/identify",
        json={"image_base64": _b64_png(), "latitude": -23.55, "longitude": -46.63},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["degraded_mode"] is True
    assert all(c["geographic_prior"] is None for c in body["top_candidates"])
    # Mesmo degradado, a jararaca (maior score) lidera e o risco é reconhecido.
    assert body["top_candidates"][0]["scientific_name"] == "Bothrops jararaca"
    assert body["overall_risk_level"] == "CRÍTICO"


def test_identify_rejects_invalid_base64() -> None:
    response = client.post(
        "/api/v1/identify",
        json={"image_base64": "!!!nao-e-base64!!!", "latitude": 0.0, "longitude": 0.0},
    )
    assert response.status_code == 400


def test_identify_validates_coordinates() -> None:
    response = client.post(
        "/api/v1/identify",
        json={"image_base64": _b64_png(), "latitude": 999.0, "longitude": 0.0},
    )
    assert response.status_code == 422  # validação Pydantic (latitude fora de faixa)


def test_health_reports_dependencies(monkeypatch) -> None:
    # Mocka os checks externos para não tocar a rede.
    async def ok_gbif():
        return "ok"

    async def ok_hf():
        return "ok"

    monkeypatch.setattr(main, "check_gbif", ok_gbif)
    monkeypatch.setattr(main, "check_huggingface", ok_hf)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["database"] == "ok"
    assert body["dependencies"]["gbif"] == "ok"
    assert body["dependencies"]["huggingface"] == "ok"
