# BioScan AI

Identificação **probabilística de animais focada em risco**. Recebe uma imagem
e coordenadas GPS e retorna espécies candidatas com probabilidades calibradas
por inferência bayesiana (visão computacional + priors geográficos do GBIF),
nível de risco e conduta segura recomendada.

> O diferencial sobre apps como iNaturalist/Seek/PictureThis: não apenas
> identifica a espécie — **avalia o risco contextualizado por localização,
> época do ano e perfil de exposição do usuário**.

## Stack

| Camada | Tecnologia |
|---|---|
| API | Python 3.11+ · FastAPI |
| Inferência de imagem | HuggingFace Inference API (ViT-Large iNat21) |
| Motor bayesiano | NumPy + SciPy (implementação manual) |
| Banco de espécies | SQLite (MVP) → PostgreSQL (produção) |
| Dados de ocorrência | GBIF · iNaturalist REST APIs |
| Testes | pytest + httpx |
| Container | Docker + docker-compose |

## Setup de desenvolvimento

```bash
# 1. Criar e ativar o ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # Linux/macOS

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
copy .env.example .env            # e preencher HF_API_KEY

# 4. Rodar a API (após Tarefa 6)
uvicorn app.main:app --reload --port 8000
```

## Estrutura

```
app/
├── main.py          # FastAPI app e routers
├── config.py        # Settings via pydantic-settings
├── models/          # Schemas Pydantic (request/response)
├── services/        # vision, bayesian, gbif, inat, risk
├── db/              # conexão, ORM e seed
└── utils/           # imagem e cache
tests/               # pytest
data/                # seed JSON + cache de ocorrências
```

## Endpoints

- `POST /api/v1/identify` — identifica espécie + risco a partir de imagem e GPS.
- `GET  /api/v1/species/{scientific_name}` — dados completos da espécie.
- `GET  /api/v1/health` — health check do serviço e dependências externas.

## Status

`v0.1.0-dev` — em construção incremental (Tarefa 1: estrutura e ambiente ✅).

## Disclaimer

Identificação probabilística. **Não substitui avaliação profissional** médica,
veterinária ou ambiental.
