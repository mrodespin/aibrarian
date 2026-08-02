# /api/app/core/ports/user_repository_port.py
"""
Puerto (Interfaz) para Repositorio de Usuarios - TFM Bibliotecario-IA

Define el CONTRATO para persistir/consultar usuarios de autenticación.
Igual que VectorDBPort o LLMPort, es una interfaz abstracta: no sabe si
detrás hay Postgres, SQLite o cualquier otra cosa.

Equivalente en TypeScript:
    interface UserRepositoryPort {
        getByEmail(email: string): Promise<User | null>;
        createUser(email: string, passwordHash: string): Promise<User>;
    }

    class UserAlreadyExistsError extends Error {}

La implementación real está en: /adapters/outbound/postgres_user_adapter.py

Contrato importante (a diferencia de VectorDBPort/LLMPort):
- Los métodos de este puerto NO deben "tragarse" errores de conexión/DB
  devolviendo un valor por defecto. Deben dejar que la excepción se
  propague. Aquí `None` significa específicamente "el usuario no existe",
  nunca "hubo un error al consultar" — si el adaptador confundiera ambos
  casos, un fallo temporal de la base de datos durante el login se
  reportaría como "credenciales inválidas", que es un bug de seguridad,
  no solo un bug funcional.
"""

from abc import ABC, abstractmethod
from typing import Optional

from app.core.domain.models import User


class UserAlreadyExistsError(Exception):
    """
    Se lanza al intentar crear un usuario cuyo email ya existe.

    Forma parte del contrato del puerto (como un "checked exception"):
    cualquier adaptador que implemente create_user debe lanzar esta
    excepción concreta ante una violación de unicidad, no una genérica.
    """
    pass


class UserRepositoryPort(ABC):
    """
    Interfaz abstracta para el almacenamiento de usuarios de autenticación.

    Superficie mínima: solo lo que necesitan el login (AuthService) y el
    script de alta de usuarios (scripts/create_user.py). No hay UI de
    registro, así que no hace falta update/delete todavía.

    Nota: ABC = Abstract Base Class
    - No se puede instanciar directamente: UserRepositoryPort() → Error
    - Solo se pueden crear clases que hereden e implementen los métodos
    """

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Busca un usuario por su email (usado como login).

        Args:
            email: Email del usuario a buscar

        Returns:
            User si existe, None si no existe.
            IMPORTANTE: los errores de conexión/DB deben propagarse
            (raise), no traducirse a None. Ver docstring del módulo.

        Ejemplo:
            user = await user_repository.get_by_email("ana@example.com")
            if user is None:
                # no existe, no "hubo un error"
                ...
        """
        pass

    @abstractmethod
    async def create_user(self, email: str, password_hash: str) -> User:
        """
        Crea un usuario nuevo.

        Args:
            email: Email del usuario (debe ser único)
            password_hash: Hash bcrypt de la contraseña (NUNCA la
                           contraseña en texto plano — eso se hashea
                           antes de llegar aquí, en el CLI/AuthService)

        Returns:
            User: el usuario recién creado (con su id asignado)

        Raises:
            UserAlreadyExistsError: si el email ya existe

        Ejemplo:
            user = await user_repository.create_user(
                "ana@example.com", "$2b$12$..."
            )
        """
        pass
