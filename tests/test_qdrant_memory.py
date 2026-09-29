"""Unit tests for Qdrant vector memory and embedding providers."""

import json
import math

import httpx
import pytest

from packages.memory.embeddings import MockEmbeddingProvider
from packages.memory.qdrant import MemoryPoint, QdrantVectorStore


@pytest.fixture
def mock_qdrant_transport():
    """Mock HTTP transport simulating Qdrant REST API endpoints."""
    collections = {}
    points_db = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        method = request.method

        # Ensure collection: GET /collections/{name}
        if method == "GET" and "/collections/" in url:
            cname = url.split("/collections/")[1].split("?")[0]
            if cname in collections:
                return httpx.Response(200, json={"result": collections[cname], "status": "ok"})
            return httpx.Response(404, json={"status": "error", "message": "Not found"})

        # Create collection: PUT /collections/{name}
        if method == "PUT" and "/collections/" in url and "/points" not in url:
            cname = url.split("/collections/")[1].split("?")[0]
            body = json.loads(request.content.decode("utf-8"))
            collections[cname] = body
            points_db.setdefault(cname, {})
            return httpx.Response(200, json={"result": True, "status": "ok"})

        # Insert points: PUT /collections/{name}/points
        if method == "PUT" and "/points" in url:
            cname = url.split("/collections/")[1].split("/points")[0]
            body = json.loads(request.content.decode("utf-8"))
            for pt in body.get("points", []):
                points_db.setdefault(cname, {})[pt["id"]] = pt
            return httpx.Response(200, json={"result": {"operation_id": 1, "status": "completed"}})

        # Delete points: POST /collections/{name}/points/delete
        if method == "POST" and "/points/delete" in url:
            cname = url.split("/collections/")[1].split("/points/delete")[0]
            body = json.loads(request.content.decode("utf-8"))
            for pid in body.get("points", []):
                points_db.get(cname, {}).pop(pid, None)
            return httpx.Response(200, json={"result": {"operation_id": 2, "status": "completed"}})

        # Search: POST /collections/{name}/points/search
        if method == "POST" and "/points/search" in url:
            cname = url.split("/collections/")[1].split("/points/search")[0]
            pts = list(points_db.get(cname, {}).values())
            results = [
                {"id": p["id"], "score": 0.95, "payload": p.get("payload", {})} for p in pts[:5]
            ]
            return httpx.Response(200, json={"result": results, "status": "ok"})

        return httpx.Response(404, json={"message": "Not found"})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimension=384)
    vec1 = await provider.embed_query("Authentication logic in FastAPI")
    vec2 = await provider.embed_query("Authentication logic in FastAPI")
    vec3 = await provider.embed_query("Something completely different")

    # Dimensions
    assert len(vec1) == 384
    # Deterministic
    assert vec1 == vec2
    assert vec1 != vec3

    # Normalized
    norm = math.sqrt(sum(x * x for x in vec1))
    assert abs(norm - 1.0) < 0.01


@pytest.mark.asyncio
async def test_qdrant_vector_store_lifecycle(mock_qdrant_transport):
    async with httpx.AsyncClient(transport=mock_qdrant_transport) as client:
        store = QdrantVectorStore(http_client=client)

        # 1. Ensure collection
        ok = await store.ensure_collection("agent_memory", vector_size=384)
        assert ok is True

        # 2. Insert points
        p1 = MemoryPoint(
            id="p-1",
            vector=[0.1] * 384,
            payload={"task_id": "123", "summary": "Fix auth error"},
        )
        p2 = MemoryPoint(
            id="p-2",
            vector=[0.2] * 384,
            payload={"task_id": "124", "summary": "Add redis caching"},
        )
        await store.insert_points("agent_memory", [p1, p2])

        # 3. Search
        search_res = await store.search("agent_memory", query_vector=[0.1] * 384, limit=2)
        assert len(search_res) == 2
        assert search_res[0].id in ("p-1", "p-2")
        assert search_res[0].score > 0.9

        # 4. Delete
        del_ok = await store.delete_points("agent_memory", ["p-1"])
        assert del_ok is True
