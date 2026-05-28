"""Conexão assíncrona com o banco de dados.

Toda I/O de banco é async (regra de desenvolvimento #1). O engine é criado a
partir da `DATABASE_URL` das settings — `sqlite+aiosqlite` no MVP, trocável por
`postgresql+asyncpg` em produção sem mudar o resto do código.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.models import Base

_settings = get_settings()


def _ensure_sqlite_dir(database_url: str) -> None:
    """Garante que o diretório do arquivo SQLite exista antes de abrir o engine.

    Sem isso, o aiosqlite falha ao criar o .db se a pasta `data/` não existir
    (ex.: clone limpo do repo, onde `data/*.db` está no .gitignore).
    """
    prefix = "sqlite+aiosqlite:///"
    if database_url.startswith(prefix):
        db_path = Path(database_url[len(prefix) :])
        db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(_settings.database_url)

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=False,
    future=True,
)

# `expire_on_commit=False` permite ler atributos do objeto após o commit sem
# disparar uma nova query (útil para serializar a resposta fora da sessão).
SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """Cria as tabelas declaradas em `Base` se ainda não existirem."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependência do FastAPI: fornece uma sessão por request e a fecha ao fim."""
    async with SessionLocal() as session:
        yield session
