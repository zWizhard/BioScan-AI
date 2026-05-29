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

# 4. Rodar a API
uvicorn app.main:app --reload --port 8000
```

## Rodar com Docker

```bash
# Pré-requisito: copiar o .env (e preencher HF_API_KEY)
copy .env.example .env

# Build + subir (a API aplica o seed no boot e expõe a porta 8000)
docker compose up --build

# Verificar
curl http://localhost:8000/api/v1/health
```

O banco SQLite é persistido no volume `bioscan-db`; o seed JSON fica imutável
dentro da imagem em `/app/data`, enquanto o `.db` vive em `/data` (volume).

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

`v0.1.0-dev` — MVP funcional. Tarefas 1–7 concluídas: estrutura, banco + seed,
cliente de visão (HuggingFace), cliente GBIF com cache, motor bayesiano,
endpoints (`/identify`, `/species`, `/health`) e containerização (Docker).
27 testes passando.

## Disclaimer

Identificação probabilística. **Não substitui avaliação profissional** médica,
veterinária ou ambiental.
