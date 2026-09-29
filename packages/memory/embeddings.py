"""Embedding abstraction for vector memory."""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract base class for vector embedding generation."""

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single text query."""

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of document strings."""


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic, normalized embedding provider for testing and offline execution."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _generate_vector(self, text: str) -> list[float]:
        # Generate pseudo-deterministic floats using sha256 chunks
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = []
        for i in range(self.dimension):
            byte_val = h[i % len(h)]
            # Normalize to [-1.0, 1.0]
            val = ((byte_val / 255.0) * 2.0) - 1.0
            raw.append(val)

        # L2-normalize
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [round(x / norm, 6) for x in raw]

    async def embed_query(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]
