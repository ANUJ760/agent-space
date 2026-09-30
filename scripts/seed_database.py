"""Database Seeding Script for Agent Space.

Idempotently provisions:
1. Default Organization ('Acme Corporation')
2. Standard User Personas with explicit RBAC roles:
   - 'admin' / 'admin@agentspace.local' (Role: ORG_ADMIN)
   - 'lead' / 'lead@agentspace.local' (Role: PROJECT_OWNER)
   - 'developer' / 'developer@agentspace.local' (Role: MEMBER)
   - 'auditor' / 'auditor@agentspace.local' (Role: VIEWER)
3. Initial Seed Project ('Platform Engineering')
"""

import asyncio
import uuid
import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import DatabaseManager
from app.auth.rbac import Role
from app.models.organization import Organization
from app.models.user import User
from app.models.project import Project
from app.models.agent import Agent
from app.models.task import Task
from app.models.project_member import ProjectMember

logger = structlog.stdlib.get_logger(__name__)


async def seed() -> None:
    settings = get_settings()
    db = DatabaseManager(settings.database)
    await db.connect()
    print("Database connected. Beginning idempotent seeding...")

    async with db._session_factory() as session:
        # 1. Seed or resolve Organization
        stmt = select(Organization).where(Organization.slug == "acme-corp")
        res = await session.execute(stmt)
        org = res.scalars().first()

        if org is None:
            org = Organization(
                id=uuid.uuid4(),
                name="Acme Corporation",
                slug="acme-corp",
                description="Enterprise workspace for autonomous AI and software engineering",
            )
            session.add(org)
            await session.flush()
            print(f"[CREATED] Organization: {org.name} ({org.slug})")
        else:
            print(f"[EXISTS]  Organization: {org.name} ({org.slug})")

        # 2. Seed Users
        seed_users = [
            {
                "username": "admin",
                "email": "admin@agentspace.local",
                "display_name": "System Administrator",
                "role": Role.ORG_ADMIN.value,
            },
            {
                "username": "lead",
                "email": "lead@agentspace.local",
                "display_name": "Engineering Lead",
                "role": Role.PROJECT_OWNER.value,
            },
            {
                "username": "developer",
                "email": "developer@agentspace.local",
                "display_name": "Senior Developer",
                "role": Role.MEMBER.value,
            },
            {
                "username": "auditor",
                "email": "auditor@agentspace.local",
                "display_name": "Security & Audit Observer",
                "role": Role.VIEWER.value,
            },
        ]

        created_users = []
        for u in seed_users:
            stmt = select(User).where(User.username == u["username"])
            res = await session.execute(stmt)
            existing_user = res.scalars().first()

            if existing_user is None:
                new_user = User(
                    id=uuid.uuid4(),
                    external_subject=f"sub-{u['username']}-{uuid.uuid4().hex[:8]}",
                    username=u["username"],
                    email=u["email"],
                    display_name=u["display_name"],
                    role=u["role"],
                    organization_id=org.id,
                    is_active=True,
                )
                session.add(new_user)
                await session.flush()
                created_users.append(new_user)
                print(f"[CREATED] User: {u['username']} (Role: {u['role']}, Email: {u['email']})")
            else:
                # Ensure correct role and organization
                if existing_user.role != u["role"]:
                    existing_user.role = u["role"]
                if existing_user.organization_id != org.id:
                    existing_user.organization_id = org.id
                await session.flush()
                print(f"[EXISTS]  User: {u['username']} (Role: {existing_user.role}, Email: {existing_user.email})")

        # 3. Seed Default Project
        stmt = select(Project).where(Project.slug == "platform-engineering")
        res = await session.execute(stmt)
        proj = res.scalars().first()

        if proj is None:
            admin_user = (await session.execute(select(User).where(User.username == "admin"))).scalars().first()
            proj = Project(
                id=uuid.uuid4(),
                organization_id=org.id,
                name="Platform Engineering",
                slug="platform-engineering",
                description="Core cloud infrastructure and autonomous AI agent pipelines",
                created_by_id=admin_user.id if admin_user else None,
            )
            session.add(proj)
            await session.flush()
            print(f"[CREATED] Project: {proj.name} ({proj.slug})")
        else:
            print(f"[EXISTS]  Project: {proj.name} ({proj.slug})")

        # 4. Seed Autonomous AI Agent
        stmt = select(Agent).where(Agent.slug == "devops-agent-01")
        res = await session.execute(stmt)
        agent = res.scalars().first()

        if agent is None:
            agent = Agent(
                id=uuid.uuid4(),
                organization_id=org.id,
                project_id=proj.id,
                name="DevOps-Agent-01",
                slug="devops-agent-01",
                description="Autonomous infrastructure & pipeline engineer with automated verification",
                role="DEVOPS_ENGINEER",
                model="claude-3-5-sonnet",
                model_provider="anthropic",
                capabilities=["ci_cd", "code_review", "container_orchestration", "security_scanning"],
                status="ACTIVE",
            )
            session.add(agent)
            await session.flush()
            print(f"[CREATED] Agent: {agent.name} ({agent.slug})")
        else:
            print(f"[EXISTS]  Agent: {agent.name} ({agent.slug})")

        # 5. Seed Project Memberships
        users_by_username = {}
        for u_row in (await session.execute(select(User))).scalars().all():
            users_by_username[u_row.username] = u_row

        memberships_to_seed = [
            ("lead", "OWNER"),
            ("developer", "MEMBER"),
            ("auditor", "VIEWER"),
        ]

        for uname, mrole in memberships_to_seed:
            u_obj = users_by_username.get(uname)
            if u_obj:
                stmt = select(ProjectMember).where(
                    ProjectMember.project_id == proj.id,
                    ProjectMember.user_id == u_obj.id,
                )
                m_existing = (await session.execute(stmt)).scalars().first()
                if not m_existing:
                    pm = ProjectMember(
                        id=uuid.uuid4(),
                        project_id=proj.id,
                        user_id=u_obj.id,
                        role=mrole,
                    )
                    session.add(pm)
                    print(f"[CREATED] ProjectMember: {uname} as {mrole}")

        await session.flush()

        # 6. Seed Tasks with Agent and Human assignments for Progress Timeline
        tasks_to_seed = [
            {
                "title": "Architecture Specification & Threat Modeling",
                "description": "Establish zero-trust boundaries and identity federation protocols across distributed agent runtimes.",
                "status": "DONE",
                "priority": "HIGH",
                "assigned_user_id": users_by_username.get("lead").id if users_by_username.get("lead") else None,
                "assigned_agent_id": None,
            },
            {
                "title": "Multi-Cloud Kubernetes Ingress Setup",
                "description": "Deploy TLS-secured Envoy gateway with rate limiting and mutual TLS authentication.",
                "status": "DONE",
                "priority": "MEDIUM",
                "assigned_user_id": users_by_username.get("developer").id if users_by_username.get("developer") else None,
                "assigned_agent_id": None,
            },
            {
                "title": "Autonomous CI/CD Deployment Pipeline",
                "description": "Provision automated pipeline with ephemeral test environments, linting gates, and synthetic canary tests.",
                "status": "IN_PROGRESS",
                "priority": "CRITICAL",
                "assigned_user_id": None,
                "assigned_agent_id": agent.id,
            },
            {
                "title": "Distributed State Synchronization & Cache Warmup",
                "description": "Implement redis pub/sub state cache synchronizer with conflict-free replicated data types.",
                "status": "IN_PROGRESS",
                "priority": "HIGH",
                "assigned_user_id": None,
                "assigned_agent_id": agent.id,
            },
            {
                "title": "Zero-Trust Service Mesh Verification",
                "description": "Verify audit logs and runtime telemetry traces for all inter-service and human-agent handoffs.",
                "status": "TODO",
                "priority": "MEDIUM",
                "assigned_user_id": users_by_username.get("developer").id if users_by_username.get("developer") else None,
                "assigned_agent_id": None,
            },
        ]

        for t_spec in tasks_to_seed:
            stmt = select(Task).where(
                Task.project_id == proj.id,
                Task.title == t_spec["title"],
            )
            existing_task = (await session.execute(stmt)).scalars().first()
            if existing_task is None:
                new_t = Task(
                    id=uuid.uuid4(),
                    organization_id=org.id,
                    project_id=proj.id,
                    title=t_spec["title"],
                    description=t_spec["description"],
                    status=t_spec["status"],
                    priority=t_spec["priority"],
                    assigned_user_id=t_spec["assigned_user_id"],
                    assigned_agent_id=t_spec["assigned_agent_id"],
                    created_by_id=users_by_username.get("admin").id if users_by_username.get("admin") else None,
                )
                session.add(new_t)
                print(f"[CREATED] Task: {t_spec['title']} (Status: {t_spec['status']})")
            else:
                print(f"[EXISTS]  Task: {t_spec['title']}")

        await session.commit()
        print("\nSeeding finished successfully.")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())
