# /api/app/core/ports/user_repository_port.py
"""
Port (Interface) for the User Repository - AIbrarian

Defines the CONTRACT for persisting/querying authentication users. Just
like VectorDBPort or LLMPort, it's an abstract interface: it doesn't
know whether Postgres, SQLite, or anything else is behind it.

TypeScript equivalent:
    interface UserRepositoryPort {
        getByEmail(email: string): Promise<User | null>;
        createUser(email: string, passwordHash: string): Promise<User>;
    }

    class UserAlreadyExistsError extends Error {}

The real implementation lives at: /adapters/outbound/postgres_user_adapter.py

Important contract detail (unlike VectorDBPort/LLMPort):
- This port's methods must NOT "swallow" connection/DB errors by
  returning a default value. They must let the exception propagate.
  Here, `None` specifically means "the user doesn't exist", never
  "there was an error querying" — if the adapter conflated the two, a
  temporary database outage during login would be reported as "invalid
  credentials", which is a security bug, not just a functional one.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.core.domain.models import User


class UserAlreadyExistsError(Exception):
    """
    Raised when trying to create a user whose email already exists.

    Part of the port's contract (like a "checked exception"): any
    adapter implementing create_user must raise this specific exception
    on a uniqueness violation, not a generic one.
    """
    pass


class UserRepositoryPort(ABC):
    """
    Abstract interface for storing authentication users.

    Minimal surface: only what login (AuthService) and the user
    creation script (scripts/create_user.py) need. There's no signup
    UI, so update/delete aren't needed yet.

    Note: ABC = Abstract Base Class
    - Can't be instantiated directly: UserRepositoryPort() → Error
    - Only subclasses that implement the methods can be created
    """

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Looks up a user by their email (used as login).

        Args:
            email: Email of the user to look up

        Returns:
            User if it exists, None if it doesn't.
            IMPORTANT: connection/DB errors must propagate (raise), not
            get translated into None. See the module docstring.

        Example:
            user = await user_repository.get_by_email("ana@example.com")
            if user is None:
                # doesn't exist, not "there was an error"
                ...
        """
        pass

    @abstractmethod
    async def create_user(self, email: str, password_hash: str) -> User:
        """
        Creates a new user.

        Args:
            email: User's email (must be unique)
            password_hash: bcrypt hash of the password (NEVER the
                           plaintext password — that's hashed before
                           reaching here, in the CLI/AuthService)

        Returns:
            User: the newly created user (with its assigned id)

        Raises:
            UserAlreadyExistsError: if the email already exists

        Example:
            user = await user_repository.create_user(
                "ana@example.com", "$2b$12$..."
            )
        """
        pass
