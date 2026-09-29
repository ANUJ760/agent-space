"""Formalized agent roles, capabilities, availability, and workload management for Agent Space."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentRole(StrEnum):
    """Standardized roles an agent can assume."""

    DEVELOPER = "DEVELOPER"
    REVIEWER = "REVIEWER"
    TESTER = "TESTER"
    RESEARCHER = "RESEARCHER"
    ARCHITECT = "ARCHITECT"
    COORDINATOR = "COORDINATOR"


class AgentCapability(StrEnum):
    """Discrete capabilities an agent can possess for scheduler matching."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    GIT = "git"
    RESEARCH = "research"
    VISION = "vision"
    DOCKER = "docker"
    GPU = "gpu"


class AgentAvailability(StrEnum):
    """Operational availability status of an agent."""

    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    PAUSED = "PAUSED"
    OFFLINE = "OFFLINE"


@dataclass
class AgentWorkload:
    """Dynamic workload tracking for an agent."""

    active_tasks: int = 0
    max_concurrent_tasks: int = 3

    @property
    def is_at_capacity(self) -> bool:
        return self.active_tasks >= self.max_concurrent_tasks

    @property
    def utilization(self) -> float:
        if self.max_concurrent_tasks <= 0:
            return 1.0
        return round(self.active_tasks / self.max_concurrent_tasks, 2)


@dataclass
class AgentProfile:
    """Complete capability and workload profile for an agent."""

    agent_id: str
    name: str
    role: AgentRole
    capabilities: set[AgentCapability] = field(default_factory=set)
    availability: AgentAvailability = AgentAvailability.AVAILABLE
    workload: AgentWorkload = field(default_factory=AgentWorkload)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_capabilities(self, required: set[AgentCapability] | list[AgentCapability]) -> bool:
        """Check if agent satisfies all required capabilities."""
        req_set = set(required)
        return req_set.issubset(self.capabilities)

    @property
    def can_accept_task(self) -> bool:
        """Return True if agent is operational and has available workload capacity."""
        return self.availability == AgentAvailability.AVAILABLE and not self.workload.is_at_capacity


class AgentCapabilityRegistry:
    """In-memory capability registry and matching service for agent dispatch."""

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        self._lock = asyncio.Lock()

    async def register(self, profile: AgentProfile) -> None:
        """Register or update an agent capability profile."""
        async with self._lock:
            self._profiles[profile.agent_id] = profile

    async def unregister(self, agent_id: str) -> bool:
        """Unregister an agent from the pool."""
        async with self._lock:
            return bool(self._profiles.pop(agent_id, None))

    async def get_profile(self, agent_id: str) -> AgentProfile | None:
        """Fetch profile for agent_id."""
        async with self._lock:
            return self._profiles.get(agent_id)

    async def set_availability(self, agent_id: str, availability: AgentAvailability) -> bool:
        """Update agent availability."""
        async with self._lock:
            profile = self._profiles.get(agent_id)
            if not profile:
                return False
            profile.availability = availability
            return True

    async def assign_task(self, agent_id: str) -> bool:
        """Increment agent active task workload."""
        async with self._lock:
            profile = self._profiles.get(agent_id)
            if not profile or not profile.can_accept_task:
                return False
            profile.workload.active_tasks += 1
            if profile.workload.is_at_capacity:
                profile.availability = AgentAvailability.BUSY
            return True

    async def release_task(self, agent_id: str) -> bool:
        """Decrement agent active task workload."""
        async with self._lock:
            profile = self._profiles.get(agent_id)
            if not profile:
                return False
            profile.workload.active_tasks = max(0, profile.workload.active_tasks - 1)
            if profile.availability == AgentAvailability.BUSY and not profile.workload.is_at_capacity:
                profile.availability = AgentAvailability.AVAILABLE
            return True

    async def find_candidates(
        self,
        required_capabilities: list[AgentCapability] | set[AgentCapability],
        role: AgentRole | None = None,
    ) -> list[AgentProfile]:
        """Find all agents matching capabilities and role that can currently accept tasks.

        Sorted by lowest workload utilization.
        """
        async with self._lock:
            candidates: list[AgentProfile] = []
            for profile in self._profiles.values():
                if role and profile.role != role:
                    continue
                if not profile.has_capabilities(required_capabilities):
                    continue
                if not profile.can_accept_task:
                    continue
                candidates.append(profile)

            # Sort by lowest utilization (least busy first)
            candidates.sort(key=lambda p: p.workload.utilization)
            return candidates

    async def find_best_agent(
        self,
        required_capabilities: list[AgentCapability] | set[AgentCapability],
        role: AgentRole | None = None,
    ) -> AgentProfile | None:
        """Return single best available agent matching requirements."""
        candidates = await self.find_candidates(required_capabilities, role)
        return candidates[0] if candidates else None


_registry = AgentCapabilityRegistry()


def get_agent_capability_registry() -> AgentCapabilityRegistry:
    """Return singleton agent capability registry."""
    return _registry
