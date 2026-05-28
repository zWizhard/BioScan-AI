"""Cache simples em memória com expiração por TTL.

Usado para não repetir chamadas à GBIF para a mesma combinação de
espécie/local/mês dentro da janela de validade (7 dias por padrão). É um cache
de processo — some quando a API reinicia, o que é aceitável no MVP; a versão de
produção pode trocar isto por Redis sem mudar os chamadores.
"""

import time
from collections.abc import Hashable
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Dicionário em memória onde cada entrada expira após `ttl_seconds`."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        # valor armazenado como (instante_de_expiração, valor).
        self._store: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        """Retorna o valor se presente e não expirado; senão None (e remove o lixo)."""
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        # time.monotonic() é imune a ajustes do relógio do sistema.
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: K, value: V) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
