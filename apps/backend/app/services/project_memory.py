"""Project Memory service combining PostgreSQL facts and Qdrant semantic memory.

Ensures:
- Strict multi-tenant and cross-project isolation.
- Every retrieval is hard-scoped to organization_id and project_id.
- Qdrant queries include mandatory filter criteria for org and project.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from packages.memory.embeddings import EmbeddingProvider
from packages.memory.qdrant import MemoryPoint, QdrantVectorStore


class MemoryAccessDeniedError(Exception):
    """Raised when an unauthorized or cross-project retrieval is attempted."""


@dataclass
class MemoryRecord:
    id: str
    organization_id: str
    project_id: str
    task_id: str | None
    memory_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    relevance_score: float = 1.0


@dataclass
class ProjectContext:
    organization_id: str
    project_id: str
    semantic_memories: list[MemoryRecord]
    facts: dict[str, Any] = field(default_factory=dict)


class ProjectMemoryService:
    """Manages project memory indexing and strictly-scoped retrieval."""

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedding_provider: EmbeddingProvider,
        collection_name: str = "agent_space_memory",
    ) -> None:
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.collection_name = collection_name

    def _build_filter(
        self,
        organization_id: uuid.UUID | str,
        project_id: uuid.UUID | str,
        task_id: uuid.UUID | str | None = None,
    ) -> dict[str, Any]:
        """Construct mandatory tenant and project isolation filters."""
        must_conditions: list[dict[str, Any]] = [
            {"key": "organization_id", "match": {"value": str(organization_id)}},
            {"key": "project_id", "match": {"value": str(project_id)}},
        ]
        if task_id:
            must_conditions.append({"key": "task_id", "match": {"value": str(task_id)}})
        return {"must": must_conditions}

    async def store_memory(
        self,
        organization_id: uuid.UUID | str,
        project_id: uuid.UUID | str,
        content: str,
        memory_type: str = "fact",
        task_id: uuid.UUID | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Embed and index a memory item scoped to a specific project."""
        point_id = str(uuid.uuid4())
        vector = await self.embedding_provider.embed_query(content)

        payload = {
            "organization_id": str(organization_id),
            "project_id": str(project_id),
            "task_id": str(task_id) if task_id else None,
            "memory_type": memory_type,
            "content": content,
            "metadata": metadata or {},
        }

        point = MemoryPoint(id=point_id, vector=vector, payload=payload)
        await self.vector_store.insert_points(self.collection_name, [point])
        return point_id

    async def retrieve_context(
        self,
        organization_id: uuid.UUID | str,
        project_id: uuid.UUID | str,
        query: str,
        limit: int = 5,
        task_id: uuid.UUID | str | None = None,
        facts: dict[str, Any] | None = None,
    ) -> ProjectContext:
        """Search memory with strict organization and project boundary enforcement."""
        query_vec = await self.embedding_provider.embed_query(query)
        filter_criteria = self._build_filter(organization_id, project_id, task_id)

        results = await self.vector_store.search(
            collection_name=self.collection_name,
            query_vector=query_vec,
            limit=limit,
            filter_criteria=filter_criteria,
        )

        memories: list[MemoryRecord] = []
        for r in results:
            payload = r.payload
            # Explicit isolation verification
            if str(payload.get("project_id")) != str(project_id):
                # Reject cross-project leak
                continue
            if str(payload.get("organization_id")) != str(organization_id):
                # Reject cross-tenant leak
                continue

            memories.append(
                MemoryRecord(
                    id=r.id,
                    organization_id=payload["organization_id"],
                    project_id=payload["project_id"],
                    task_id=payload.get("task_id"),
                    memory_type=payload.get("memory_type", "fact"),
                    content=payload.get("content", ""),
                    metadata=payload.get("metadata", {}),
                    relevance_score=r.score,
                )
            )

        return ProjectContext(
            organization_id=str(organization_id),
            project_id=str(project_id),
            semantic_memories=memories,
            facts=facts or {},
        )
