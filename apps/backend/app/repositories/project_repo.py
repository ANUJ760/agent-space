"""Repository for Project database operations with strict organization scoping."""

import uuid

from sqlalchemy import func, select

from app.models.project import Project
from app.repositories import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Data access repository for Project entities.

    Enforces organization-scoped data isolation across all query operations.
    """

    model_class = Project

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Project]:
        """List all projects strictly belonging to the given organization."""
        stmt = (
            select(Project)
            .where(Project.organization_id == organization_id)
            .offset(offset)
            .limit(limit)
            .order_by(Project.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_org(
        self,
        project_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> Project | None:
        """Fetch a project by ID ensuring it belongs to the given organization."""
        stmt = select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_slug_and_org(
        self,
        slug: str,
        organization_id: uuid.UUID,
    ) -> Project | None:
        """Fetch a project by slug ensuring it belongs to the given organization."""
        stmt = select(Project).where(
            Project.slug == slug,
            Project.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count_by_organization(self, organization_id: uuid.UUID) -> int:
        """Count total projects in an organization."""
        stmt = select(func.count(Project.id)).where(Project.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0
