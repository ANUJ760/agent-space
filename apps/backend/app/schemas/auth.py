"""Authentication request and response schemas."""

from pydantic import BaseModel, Field

from app.schemas.user import UserProfileResponse


class LoginRequest(BaseModel):
    """Payload for POST /api/v1/auth/login."""

    username: str = Field(..., min_length=1, max_length=100, description="Username or email")
    password: str = Field(..., min_length=1, max_length=1024, description="Account password")


class RegisterRequest(BaseModel):
    """Payload for POST /api/v1/auth/register."""

    username: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    email: str = Field(..., min_length=3, max_length=255, description="User corporate or personal email")
    password: str = Field(..., min_length=8, max_length=1024, description="User password")
    display_name: str | None = Field(default=None, max_length=255)
    organization_name: str | None = Field(default=None, max_length=100, description="Target or new organization name")


class AuthTokenResponse(BaseModel):
    """Token response returned upon successful authentication or registration."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 86400
    user: UserProfileResponse
