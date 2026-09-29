"""Unit tests for ProjectMemoryService multi-tenant scoping and cross-project isolation."""

import uuid

import pytest
from app.services.project_memory import ProjectMemoryService

from packages.memory.embeddings import MockEmbeddingProvider
from packages.memory.qdrant import MemoryPoint, QdrantVectorStore


class MockVectorStore(QdrantVectorStore):
    def __init__(self):
        super().__init__()
        self.points: dict[str, list[MemoryPoint]] = {}

    async def insert_points(self, collection_name: str, points: list[MemoryPoint]):
        self.points.setdefault(collection_name, []).extend(points)
        return True

    async def search(self, collection_name: str, query_vector, limit=10, filter_criteria=None):
        all_pts = self.points.get(collection_name, [])
        # Apply filter matching
        filtered = []
        for p in all_pts:
            match = True
            if filter_criteria and "must" in filter_criteria:
                for cond in filter_criteria["must"]:
                    key = cond["key"]
                    expected = cond["match"]["value"]
                    if str(p.payload.get(key)) != str(expected):
                        match = False
                        break
            if match:
                from packages.memory.qdrant import SearchResult

                filtered.append(SearchResult(id=p.id, score=0.92, payload=p.payload))
        return filtered[:limit]


@pytest.mark.asyncio
async def test_project_memory_scoping_and_isolation():
    vec_store = MockVectorStore()
    embedding_provider = MockEmbeddingProvider(dimension=64)
    service = ProjectMemoryService(
        vector_store=vec_store,
        embedding_provider=embedding_provider,
        collection_name="project_memory",
    )

    org_id = uuid.uuid4()
    proj_a_id = uuid.uuid4()
    proj_b_id = uuid.uuid4()

    # Store memory for Project A
    await service.store_memory(
        organization_id=org_id,
        project_id=proj_a_id,
        content="Project A uses Postgres 16 and FastAPI",
        memory_type="architecture",
    )

    # Store memory for Project B
    await service.store_memory(
        organization_id=org_id,
        project_id=proj_b_id,
        content="Project B uses MongoDB and Go",
        memory_type="architecture",
    )

    # 1. Retrieve for Project A
    ctx_a = await service.retrieve_context(
        organization_id=org_id,
        project_id=proj_a_id,
        query="What database is used?",
    )
    assert len(ctx_a.semantic_memories) == 1
    assert "FastAPI" in ctx_a.semantic_memories[0].content
    assert "MongoDB" not in ctx_a.semantic_memories[0].content

    # 2. Retrieve for Project B (strict isolation: never gets Project A)
    ctx_b = await service.retrieve_context(
        organization_id=org_id,
        project_id=proj_b_id,
        query="What database is used?",
    )
    assert len(ctx_b.semantic_memories) == 1
    assert "MongoDB" in ctx_b.semantic_memories[0].content
    assert "FastAPI" not in ctx_b.semantic_memories[0].content

    # 3. Nonexistent project gets 0 memories
    ctx_empty = await service.retrieve_context(
        organization_id=org_id,
        project_id=uuid.uuid4(),
        query="database",
    )
    assert len(ctx_empty.semantic_memories) == 0
