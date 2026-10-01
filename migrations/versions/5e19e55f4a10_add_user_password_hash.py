"""Add password hashes for local account authentication.

Existing accounts remain locked until an operator assigns a password. No
published demo password is silently installed during migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e19e55f4a10"
down_revision: str | None = "2ff43615bc2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
