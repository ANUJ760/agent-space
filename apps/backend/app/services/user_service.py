"""User identity reconciliation service.

Maps external Keycloak token subject identities to internal database User records.
Provides automatic user provisioning and organization bootstrap on first login.
"""

from app.auth.models import AuthenticatedUser
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.user_repo import UserRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


async def reconcile_user(
    session: AsyncSession,
    auth_user: AuthenticatedUser,
) -> User:
    """Reconcile an AuthenticatedUser against the database.

    1. Looks up the User by external_subject (Keycloak sub claim).
    2. If found, updates mutable attributes (email, username, display_name) if changed.
    3. If not found, provisions a new User:
       - If no organizations exist, creates a default organization and sets role=ORG_ADMIN.
       - If an organization exists, attaches the user to the primary organization.
    4. Returns the User with organization eagerly loaded.
    """
    user_repo = UserRepository(session)
    org_repo = OrganizationRepository(session)

    # 1. Lookup user by immutable external subject
    stmt = (
        select(User)
        .where(User.external_subject == auth_user.id)
        .options(selectinload(User.organization))
    )
    result = await session.execute(stmt)
    user = result.scalars().first()

    if user is not None:
        # Synchronize attributes from Keycloak
        modified = False
        if auth_user.email and user.email != auth_user.email:
            user.email = auth_user.email
            modified = True
        if auth_user.username and user.username != auth_user.username:
            user.username = auth_user.username
            modified = True
        if modified:
            await session.flush()
        return user

    # 2. First-time provisioning: check for existing organizations
    all_orgs = await org_repo.list_all(limit=1)
    if not all_orgs:
        # Bootstrap default organization
        default_org = Organization(
            name="Default Organization",
            slug="default-org",
            description="Default organization for Agent Space",
        )
        await org_repo.create(default_org)
        org_id = default_org.id
        role = "SYSTEM_ADMIN" if "admin" in auth_user.roles else "ORG_ADMIN"
    else:
        org_id = all_orgs[0].id
        role = "ORG_ADMIN" if "admin" in auth_user.roles else "MEMBER"

    # 3. Create the internal User record
    new_user = User(
        external_subject=auth_user.id,
        email=auth_user.email or f"{auth_user.username}@agentspace.local",
        username=auth_user.username,
        display_name=auth_user.username,
        role=role,
        organization_id=org_id,
    )
    await user_repo.create(new_user)

    # Reload with organization eager load
    stmt = select(User).where(User.id == new_user.id).options(selectinload(User.organization))
    res = await session.execute(stmt)
    loaded_user = res.scalars().one()
    return loaded_user
