"""Motor de inferência bayesiana do BioScan AI.

Combina a verossimilhança do modelo de visão com um prior geográfico/sazonal
derivado de ocorrências do GBIF, segundo:

    P(espécie_i | imagem, local, época)
        ∝ P(imagem | espécie_i) · P(espécie_i | local, época)

onde a verossimilhança é o `score` do ViT e o prior é proporcional à densidade
de ocorrências validadas no raio e na janela sazonal. O efeito desejado de
produto: uma espécie perigosa que o modelo vê a 40% mas sem registros locais cai
no ranking; uma espécie comum na região com 35% sobe.

Decisões de modelagem (cientista de dados):
- **Laplace (add-α) smoothing** no prior: espécies sem registros recebem massa
  mínima não-nula — nunca somem do ranking, o que é crítico num produto de risco
  (um falso-negativo de espécie venenosa é o pior erro possível).
- **Normalização vetorizada com NumPy** e guarda contra denominador nulo.
- **Consultas GBIF concorrentes** (asyncio.gather) sobre um único AsyncClient,
  para caber no orçamento de latência do MVP.
"""

import asyncio
import logging
from typing import Any

import httpx
import numpy as np

from app.config import get_settings
from app.services import gbif

logger = logging.getLogger("bioscan.bayesian")
settings = get_settings()


async def compute_geographic_prior(
    species_list: list[str],
    lat: float,
    lng: float,
    month: int,
    radius_km: int | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, float]:
    """Retorna {nome_científico: prior_normalizado}.

    O prior é proporcional ao nº de ocorrências validadas no GBIF dentro do raio
    e na janela sazonal (±1 mês), com Laplace smoothing (add-α): espécies sem
    registros recebem prior mínimo não-nulo. Os priors somam 1.0.
    """
    if not species_list:
        return {}

    alpha = settings.prior_smoothing_alpha

    # Um único client compartilhado + gather: as N consultas ao GBIF correm em
    # paralelo em vez de serialmente (essencial para a latência alvo de <8s).
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=gbif.REQUEST_TIMEOUT)

    try:
        counts = await asyncio.gather(
            *(
                gbif.get_occurrence_count(species, lat, lng, month, radius_km, client=client)
                for species in species_list
            )
        )
    finally:
        if owns_client:
            await client.aclose()

    # Laplace smoothing: count + α garante massa de probabilidade > 0 para todas.
    smoothed = np.asarray(counts, dtype=float) + alpha
    priors = smoothed / smoothed.sum()

    return {species: float(p) for species, p in zip(species_list, priors)}


async def bayesian_inference(
    model_scores: list[dict],
    lat: float,
    lng: float,
    month: int,
    radius_km: int | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Combina likelihood do modelo com o prior geográfico e retorna o posterior.

    `model_scores`: [{"label": str, "score": float}, ...] (saída do ViT).
    Retorno: lista ordenada por probabilidade posterior decrescente, cada item
    com `species`, `probability`, `model_confidence` e `geographic_prior` —
    campos já no formato que o endpoint /identify expõe.
    """
    if not model_scores:
        return []

    species_names = [s["label"] for s in model_scores]
    likelihoods = {s["label"]: float(s["score"]) for s in model_scores}

    priors = await compute_geographic_prior(
        species_names, lat, lng, month, radius_km, client=client
    )

    like = np.asarray([likelihoods[sp] for sp in species_names], dtype=float)
    prior = np.asarray([priors[sp] for sp in species_names], dtype=float)
    unnormalized = like * prior
    total = unnormalized.sum()

    if total > 0:
        posterior = unnormalized / total
    else:
        # Degenerado (todas as likelihoods ~0): cai para o prior puro em vez de
        # dividir por zero — preserva o ranking geográfico e a soma 1.0.
        logger.warning("Posterior degenerado (likelihood·prior=0); usando prior puro.")
        posterior = prior / prior.sum()

    results = [
        {
            "species": sp,
            "probability": float(post),
            "model_confidence": likelihoods[sp],
            "geographic_prior": priors[sp],
        }
        for sp, post in zip(species_names, posterior)
    ]
    results.sort(key=lambda item: item["probability"], reverse=True)
    return results
