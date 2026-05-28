"""Testes do motor bayesiano (Tarefa 5).

Dados sintéticos: a contagem do GBIF é mockada (monkeypatch), de modo que cada
teste controla exatamente os priors. Nenhuma chamada de rede é feita.
"""

import pytest

from app.services import bayesian


def _patch_counts(monkeypatch, counts: dict[str, int]) -> None:
    """Substitui gbif.get_occurrence_count por um mapa fixo espécie -> contagem."""

    async def fake_get_occurrence_count(
        scientific_name, lat, lng, month, radius_km=None, *, client=None
    ):
        return counts[scientific_name]

    monkeypatch.setattr(bayesian.gbif, "get_occurrence_count", fake_get_occurrence_count)


# ---- compute_geographic_prior ----

@pytest.mark.asyncio
async def test_prior_normalizes_to_one(monkeypatch) -> None:
    _patch_counts(monkeypatch, {"A": 100, "B": 0, "C": 5})
    priors = await bayesian.compute_geographic_prior(["A", "B", "C"], -23.5, -46.6, 5)
    assert sum(priors.values()) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_prior_zero_count_gets_minimal_nonzero_mass(monkeypatch) -> None:
    # Laplace smoothing: espécie sem registros (B) não pode receber prior 0.
    _patch_counts(monkeypatch, {"A": 100, "B": 0, "C": 5})
    priors = await bayesian.compute_geographic_prior(["A", "B", "C"], -23.5, -46.6, 5)
    assert priors["B"] > 0
    # E deve ser a menor massa entre as três (menos ocorrências).
    assert priors["B"] < priors["C"] < priors["A"]


# ---- bayesian_inference ----

@pytest.mark.asyncio
async def test_posterior_sums_to_one(monkeypatch) -> None:
    _patch_counts(monkeypatch, {"A": 100, "B": 0, "C": 5})
    scores = [
        {"label": "A", "score": 0.30},
        {"label": "B", "score": 0.60},
        {"label": "C", "score": 0.10},
    ]
    results = await bayesian.bayesian_inference(scores, -23.5, -46.6, 5)
    assert sum(r["probability"] for r in results) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_species_with_zero_prior_stays_in_ranking(monkeypatch) -> None:
    # Critério da tarefa: prior mínimo (Laplace ≠ 0) não some do ranking.
    _patch_counts(monkeypatch, {"A": 100, "B": 0, "C": 5})
    scores = [
        {"label": "A", "score": 0.30},
        {"label": "B", "score": 0.60},
        {"label": "C", "score": 0.10},
    ]
    results = await bayesian.bayesian_inference(scores, -23.5, -46.6, 5)
    ranked_species = {r["species"] for r in results}
    assert ranked_species == {"A", "B", "C"}
    b = next(r for r in results if r["species"] == "B")
    assert b["probability"] > 0


@pytest.mark.asyncio
async def test_highest_likelihood_times_prior_ranks_first(monkeypatch) -> None:
    # Top do ranking deve ser o argmax de likelihood·prior.
    counts = {"A": 100, "B": 0, "C": 5}
    _patch_counts(monkeypatch, counts)
    scores = [
        {"label": "A", "score": 0.30},
        {"label": "B", "score": 0.60},
        {"label": "C", "score": 0.10},
    ]
    results = await bayesian.bayesian_inference(scores, -23.5, -46.6, 5)

    # Reproduz o cálculo de forma independente (α=1 por padrão).
    alpha = bayesian.settings.prior_smoothing_alpha
    smoothed = {k: v + alpha for k, v in counts.items()}
    total_prior = sum(smoothed.values())
    likelihood = {s["label"]: s["score"] for s in scores}
    products = {k: likelihood[k] * (smoothed[k] / total_prior) for k in counts}
    expected_top = max(products, key=products.get)

    assert results[0]["species"] == expected_top


@pytest.mark.asyncio
async def test_geographic_prior_overrides_high_confidence_rare_species(monkeypatch) -> None:
    """Tese central do produto: o prior geográfico reordena o ranking do modelo.

    `Venenosa_rara` tem alta confiança do modelo (0.40) mas ZERO registros
    locais; `Comum_local` tem confiança menor (0.35) e muitos registros. Após a
    combinação bayesiana, a espécie comum na região deve superar a rara.
    """
    _patch_counts(monkeypatch, {"Venenosa_rara": 0, "Comum_local": 5000})
    scores = [
        {"label": "Venenosa_rara", "score": 0.40},
        {"label": "Comum_local", "score": 0.35},
    ]
    results = await bayesian.bayesian_inference(scores, -23.5, -46.6, 5)

    assert results[0]["species"] == "Comum_local"
    # A espécie rara não some — apenas perde o topo (segurança: nunca descartar).
    assert any(r["species"] == "Venenosa_rara" for r in results)
