"""Repository for Agent database operations."""

import uuid

from sqlalchemy import func, or_, select

from app.models.agent import Agent
from app.repositories import BaseRepository


class AgentRepository(BaseRepository[Agent]):
    """Data access repository for Agent definitions and capabilities."""

    model_class = Agent

    async def list_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
        status: str | None = None,
        role: str | None = None,
    ) -> list[Agent]:
        """List all agents belonging to an organization, optionally filtered."""
        stmt = (
            select(Agent)
            .where(Agent.organization_id == organization_id)
            .offset(offset)
            .limit(limit)
            .order_by(Agent.name.asc())
        )
        if status:
            stmt = stmt.where(Agent.status == status)
        if role:
            stmt = stmt.where(Agent.role == role)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
        include_org_level: bool = True,
    ) -> list[Agent]:
        """List agents available to a specific project.

        If include_org_level is True, includes both project-scoped agents
        and organization-wide agents (where project_id is None).
        """
        if include_org_level:
            condition = or_(
                Agent.project_id == project_id,
                (Agent.organization_id == organization_id) & (Agent.project_id.is_(None)),
            )
        else:
            condition = Agent.project_id == project_id

        stmt = (
            select(Agent)
            .where(Agent.organization_id == organization_id, condition)
            .offset(offset)
            .limit(limit)
            .order_by(Agent.name.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_org_and_slug(self, organization_id: uuid.UUID, slug: str) -> Agent | None:
        """Find an agent by organization ID and unique URL slug."""
        stmt = select(Agent).where(
            Agent.organization_id == organization_id,
            Agent.slug == slug,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def count_by_organization(self, organization_id: uuid.UUID) -> int:
        """Return total number of agents registered under an organization."""
        stmt = select(func.count(Agent.id)).where(Agent.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0
