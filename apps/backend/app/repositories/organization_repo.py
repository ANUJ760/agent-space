"""Repository for Organization database operations."""

from sqlalchemy import select

from app.models.organization import Organization
from app.repositories import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Data access repository for Organization entities."""

    model_class = Organization

    async def get_by_slug(self, slug: str) -> Organization | None:
        """Fetch an organization by unique URL slug."""
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Organization | None:
        """Fetch an organization by exact name."""
        stmt = select(Organization).where(Organization.name == name)
        result = await self._session.execute(stmt)
        return result.scalars().first()
