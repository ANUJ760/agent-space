"""Repository base classes and domain repositories for data access."""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository for CRUD operations on a SQLAlchemy model."""

    model_class: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: uuid.UUID) -> ModelT | None:
        """Fetch a single entity by its primary key UUID."""
        return await self._session.get(self.model_class, entity_id)

    async def list_all(self, *, offset: int = 0, limit: int = 100) -> list[ModelT]:
        """Return a paginated list of entities."""
        stmt = select(self.model_class).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: ModelT) -> ModelT:
        """Add a new entity to the session and flush to obtain generated values."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        """Merge an updated entity and flush."""
        merged = await self._session.merge(entity)
        await self._session.flush()
        return merged

    async def delete(self, entity: ModelT) -> None:
        """Mark an entity for deletion."""
        await self._session.delete(entity)
        await self._session.flush()


from app.repositories.organization_repo import OrganizationRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402

__all__ = [
    "BaseRepository",
    "OrganizationRepository",
    "UserRepository",
]
