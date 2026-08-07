#!/usr/bin/env python3
# /scripts/create_user.py
"""
User Creation CLI - AIbrarian

There is no signup UI in the frontend: users who can log in are created
EXCLUSIVELY with this script, which stores them in Postgres (Neon in
production, the local container in development).

Prerequisite:
    DATABASE_URL configured in .env or as an environment variable.

Usage:
    python scripts/create_user.py --email ana@example.com
    # Prompts for the password interactively (getpass), twice to
    # confirm. It is NOT passed as an argument: it would end up in the
    # shell history.

To create the first user against production (Neon), before deploying
the backend:
    DATABASE_URL=<Neon connection string> python scripts/create_user.py --email you@email.com
"""

# ============================================================================
# IMPORTS
# ============================================================================
import asyncio
import argparse
import getpass
import logging
import sys
from pathlib import Path

# ============================================================================
# PATH SETUP
# ============================================================================
# Same pattern as ingest_notion.py: adds api/ to the path so Python finds
# the "app" package when the script is run directly.
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import bcrypt

from app.config.settings import settings
from app.adapters.outbound.postgres_user_adapter import PostgresUserAdapter
from app.core.ports.user_repository_port import UserAlreadyExistsError


# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


MIN_PASSWORD_LENGTH = 8


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
async def main():
    parser = argparse.ArgumentParser(
        description="Create a new user for AIbrarian (no signup UI, this script is the only way)"
    )
    parser.add_argument(
        "--email",
        "-e",
        required=True,
        help="User's email (used as login)"
    )
    args = parser.parse_args()

    print("\n" + "="*60)
    print("📚 AIbrarian - Create User")
    print("="*60 + "\n")

    if not settings.database_url:
        logger.error("❌ DATABASE_URL not configured!")
        logger.error("   Set it in api/.env (local development) or as an")
        logger.error("   environment variable (e.g. to create the first user in Neon)")
        sys.exit(1)

    # getpass instead of an argparse flag: a password passed as an
    # argument would end up in the shell history (~/.bash_history, etc.)
    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        logger.error("❌ Passwords don't match")
        sys.exit(1)

    if len(password) < MIN_PASSWORD_LENGTH:
        logger.error(f"❌ Password must be at least {MIN_PASSWORD_LENGTH} characters")
        sys.exit(1)

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    adapter = PostgresUserAdapter()
    try:
        # connect() creates the pool AND the `users` table if it doesn't
        # exist yet (idempotent), so no separate "init schema" step is needed.
        await adapter.connect()
        user = await adapter.create_user(args.email, password_hash)
        print(f"\n✅ User created: {user.email} (id={user.id})\n")
    except UserAlreadyExistsError:
        logger.error(f"❌ A user with email '{args.email}' already exists")
        sys.exit(1)
    finally:
        await adapter.close()


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
