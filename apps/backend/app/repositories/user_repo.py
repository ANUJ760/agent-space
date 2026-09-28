"""Repository for User database operations."""

import uuid

from sqlalchemy import select

from app.models.user import User
from app.repositories import BaseRepository


class UserRepository(BaseRepository[User]):
    """Data access repository for User entities."""

    model_class = User

    async def get_by_external_subject(self, sub: str) -> User | None:
        """Fetch a user by their permanent Keycloak subject UUID."""
        stmt = select(User).where(User.external_subject == sub)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str) -> User | None:
        """Fetch a user by username."""
        stmt = select(User).where(User.username == username)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_by_organization(self, organization_id: uuid.UUID) -> list[User]:
        """List all users belonging to a specific organization."""
        stmt = select(User).where(User.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
