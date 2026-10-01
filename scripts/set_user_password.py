"""Set a local account password interactively after the auth migration.

Run with PYTHONPATH=apps/backend:. python3 scripts/set_user_password.py USERNAME.
The password is read without terminal echo and is never passed on the command line.
"""

import argparse
import asyncio
import getpass

from sqlalchemy import or_, select

from app.auth.passwords import hash_password
from app.config import get_settings
from app.database import DatabaseManager
from app.models import User


async def set_password(identifier: str, password: str) -> None:
    db = DatabaseManager(get_settings().database)
    await db.connect()
    try:
        async with db.session_factory() as session:
            rows = (
                await session.execute(
                    select(User).where(or_(User.username == identifier, User.email == identifier))
                )
            ).scalars().all()
            if len(rows) != 1:
                raise ValueError("Expected exactly one matching account; use a unique username or email")
            rows[0].password_hash = await asyncio.to_thread(hash_password, password)
            await session.commit()
    finally:
        await db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set a local account password")
    parser.add_argument("username", help="Existing username or email")
    args = parser.parse_args()
    entered = getpass.getpass("New password: ")
    if len(entered) < 8 or len(entered) > 1024:
        parser.error("Password must contain 8 to 1024 characters")
    if entered != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    asyncio.run(set_password(args.username, entered))
    print("Password updated")
