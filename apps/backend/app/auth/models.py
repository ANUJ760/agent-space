"""Authentication models for Agent Space backend."""

from typing import Any

from pydantic import BaseModel, Field


class AuthenticatedUser(BaseModel):
    """Represents an authenticated actor verified via Keycloak OIDC JWT.

    Uses Keycloak's Subject claim (sub) as the immutable, permanent external
    identity key rather than mutable email addresses.
    """

    id: str = Field(description="Keycloak Subject UUID (sub claim) - stable external identity")
    username: str = Field(description="Preferred username from Keycloak token")
    email: str | None = Field(default=None, description="User email address")
    email_verified: bool = Field(
        default=False, description="Whether email has been verified in Keycloak"
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Aggregated realm and resource client roles",
    )
    raw_claims: dict[str, Any] = Field(
        default_factory=dict,
        description="Complete raw JWT claims payload for downstream inspection",
    )
