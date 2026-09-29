"""Qdrant vector store client for semantic memory search.

Adheres strictly to the principle:
- Qdrant is an index accelerator, NEVER authoritative.
- PostgreSQL remains the authoritative source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


class QdrantError(Exception):
    """Base exception for Qdrant operations."""


@dataclass
class MemoryPoint:
    """A semantic vector memory point."""

    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Result of a semantic search query."""

    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class QdrantVectorStore:
    """Async Qdrant REST client for collection management, point indexing, and search."""

    def __init__(
        self,
        base_url: str = "http://localhost:6333",
        api_key: str | None = None,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._custom_client = http_client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers = self._headers()

        if self._custom_client:
            resp = await self._custom_client.request(
                method, url, headers=headers, json=json_data, timeout=self.timeout
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method, url, headers=headers, json=json_data, timeout=self.timeout
                )

        if resp.status_code >= 400:
            raise QdrantError(f"Qdrant error {resp.status_code} on {method} {path}: {resp.text}")
        return resp

    async def ensure_collection(
        self,
        collection_name: str,
        vector_size: int = 384,
        distance: str = "Cosine",
    ) -> bool:
        """Create collection if it does not already exist."""
        # Check if collection exists
        try:
            resp = await self._request("GET", f"/collections/{collection_name}")
            if resp.status_code == 200:
                return True
        except QdrantError:
            pass

        # Create collection
        payload = {
            "vectors": {
                "size": vector_size,
                "distance": distance,
            }
        }
        await self._request("PUT", f"/collections/{collection_name}", json_data=payload)
        return True

    async def insert_points(
        self,
        collection_name: str,
        points: list[MemoryPoint],
    ) -> bool:
        """Insert or upsert vector points into a collection."""
        if not points:
            return True

        formatted = [{"id": p.id, "vector": p.vector, "payload": p.payload} for p in points]
        payload = {"points": formatted}
        await self._request(
            "PUT",
            f"/collections/{collection_name}/points?wait=true",
            json_data=payload,
        )
        return True

    async def delete_points(
        self,
        collection_name: str,
        point_ids: list[str],
    ) -> bool:
        """Delete specific points by ID."""
        if not point_ids:
            return True

        payload = {"points": point_ids}
        await self._request(
            "POST",
            f"/collections/{collection_name}/points/delete?wait=true",
            json_data=payload,
        )
        return True

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        filter_criteria: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Execute semantic search against indexed vector points."""
        payload: dict[str, Any] = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True,
        }
        if filter_criteria:
            payload["filter"] = filter_criteria

        resp = await self._request(
            "POST",
            f"/collections/{collection_name}/points/search",
            json_data=payload,
        )
        data = resp.json()
        results = data.get("result", [])

        return [
            SearchResult(
                id=str(r.get("id")),
                score=float(r.get("score", 0.0)),
                payload=r.get("payload", {}),
            )
            for r in results
        ]
