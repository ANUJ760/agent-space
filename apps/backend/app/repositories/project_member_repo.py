"""Repository for ProjectMember database operations."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.project_member import ProjectMember
from app.repositories import BaseRepository


class ProjectMemberRepository(BaseRepository[ProjectMember]):
    """Data access repository for ProjectMember associations."""

    model_class = ProjectMember

    async def get_by_project_and_user(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProjectMember | None:
        """Find a membership record by project ID and user ID."""
        stmt = (
            select(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
            .options(selectinload(ProjectMember.user))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ProjectMember]:
        """List all member records for a project with user eagerly loaded."""
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .options(selectinload(ProjectMember.user))
            .offset(offset)
            .limit(limit)
            .order_by(ProjectMember.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(self, project_id: uuid.UUID) -> int:
        """Count total members assigned to a project."""
        stmt = select(func.count(ProjectMember.id)).where(ProjectMember.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def count_owners(self, project_id: uuid.UUID) -> int:
        """Count the number of owners for a project."""
        stmt = select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "PROJECT_OWNER",
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0
