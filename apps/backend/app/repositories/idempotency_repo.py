"""Repository for IdempotencyRecord persistence and lookup."""

from sqlalchemy import select, update

from app.models.idempotency import IdempotencyRecord
from app.repositories import BaseRepository


class IdempotencyRepository(BaseRepository[IdempotencyRecord]):
    """Data access layer for idempotency records."""

    async def get_by_key(self, key: str) -> IdempotencyRecord | None:
        """Fetch an idempotency record by unique key."""
        stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_processing_record(
        self,
        key: str,
        request_hash: str,
        request_method: str,
        request_path: str,
    ) -> IdempotencyRecord:
        """Create a new idempotency record in PROCESSING state."""
        record = IdempotencyRecord(
            key=key,
            request_hash=request_hash,
            request_method=request_method,
            request_path=request_path,
            status="PROCESSING",
        )
        return await self.create(record)

    async def complete_record(
        self,
        key: str,
        status_code: int,
        response_headers: dict[str, str],
        response_body: str,
    ) -> None:
        """Update an idempotency record with the completed response payload."""
        stmt = (
            update(IdempotencyRecord)
            .where(IdempotencyRecord.key == key)
            .values(
                status="COMPLETED",
                response_status_code=status_code,
                response_headers=response_headers,
                response_body=response_body,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
