"""Testes da rota de detalhe de espécie e do health check (Tarefa 2)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_species_found() -> None:
    response = client.get("/api/v1/species/Bothrops jararaca")
    assert response.status_code == 200
    body = response.json()
    assert body["common_name_pt"] == "Jararaca"
    assert body["risk_level"] == "CRÍTICO"
    assert body["venom_type"] == "HEMOTÓXICO"


def test_get_species_is_case_insensitive() -> None:
    # O output do modelo de visão e a digitação do usuário variam na capitalização.
    response = client.get("/api/v1/species/bothrops JARARACA")
    assert response.status_code == 200
    assert response.json()["scientific_name"] == "Bothrops jararaca"


def test_get_species_not_found_returns_404() -> None:
    response = client.get("/api/v1/species/Especie inexistente")
    assert response.status_code == 404
    assert "não encontrada" in response.json()["detail"]
