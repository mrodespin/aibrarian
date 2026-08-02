#!/usr/bin/env python3
# /scripts/create_user.py
"""
Script CLI de Alta de Usuarios - TFM Bibliotecario-IA

No hay UI de registro en el frontend: los usuarios que pueden iniciar
sesión se dan de alta EXCLUSIVAMENTE con este script, que los guarda en
Postgres (Neon en producción, el contenedor local en desarrollo).

Requisito previo:
    DATABASE_URL configurada en .env o como variable de entorno.

Uso:
    python scripts/create_user.py --email ana@example.com
    # Pide la contraseña de forma interactiva (getpass), dos veces para
    # confirmar. NO se pasa por argumento: quedaría en el historial de
    # la shell.

Para dar de alta el primer usuario contra producción (Neon), antes de
desplegar el backend:
    DATABASE_URL=<connection string de Neon> python scripts/create_user.py --email tu@email.com
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
# CONFIGURACIÓN DE PATH
# ============================================================================
# Mismo patrón que ingest_notion.py: añade api/ al path para que Python
# encuentre el paquete "app" al ejecutar el script directamente.
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import bcrypt

from app.config.settings import settings
from app.adapters.outbound.postgres_user_adapter import PostgresUserAdapter
from app.core.ports.user_repository_port import UserAlreadyExistsError


# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


MIN_PASSWORD_LENGTH = 8


# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================
async def main():
    parser = argparse.ArgumentParser(
        description="Create a new user for Bibliotecario-IA (no hay UI de registro, solo este script)"
    )
    parser.add_argument(
        "--email",
        "-e",
        required=True,
        help="Email del usuario (se usa como login)"
    )
    args = parser.parse_args()

    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - Create User")
    print("="*60 + "\n")

    if not settings.database_url:
        logger.error("❌ DATABASE_URL not configured!")
        logger.error("   Set it in api/.env (desarrollo local) o como variable")
        logger.error("   de entorno (p.ej. para crear el primer usuario en Neon)")
        sys.exit(1)

    # getpass en vez de un flag de argparse: una contraseña pasada como
    # argumento quedaría en el historial de la shell (~/.bash_history, etc.)
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
        # connect() crea el pool Y la tabla `users` si no existe (idempotente),
        # así que no hace falta un paso de "init schema" aparte.
        await adapter.connect()
        user = await adapter.create_user(args.email, password_hash)
        print(f"\n✅ User created: {user.email} (id={user.id})\n")
    except UserAlreadyExistsError:
        logger.error(f"❌ A user with email '{args.email}' already exists")
        sys.exit(1)
    finally:
        await adapter.close()


# ============================================================================
# BLOQUE DE ENTRADA
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
