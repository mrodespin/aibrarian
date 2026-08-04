# /api/app/core/ports/conversation_repository_port.py
"""
Puerto (Interfaz) para Repositorio de Historial de Conversación - TFM Bibliotecario-IA

Define el CONTRATO para persistir/consultar los turnos (mensajes) de una
conversación. Mismo patrón que UserRepositoryPort: interfaz abstracta, no
sabe si detrás hay Postgres o cualquier otra cosa.

Equivalente en TypeScript:
    interface ConversationRepositoryPort {
        appendMessage(sessionId: string, userId: number, role: string, content: string): Promise<void>;
        getRecentMessages(sessionId: string, userId: number, limit: number): Promise<ConversationMessage[]>;
    }

La implementación real está en: /adapters/outbound/postgres_conversation_adapter.py

Contrato importante (igual que UserRepositoryPort): los errores de
conexión/DB deben propagarse, no traducirse silenciosamente en "sin
historial" — quien llama (ConversationService / el endpoint /ask) decide
cómo degradar (loguear y continuar sin historial), no el puerto.
"""

from abc import ABC, abstractmethod
from typing import List

from app.core.domain.models import ConversationMessage


class ConversationRepositoryPort(ABC):
    """
    Interfaz abstracta para el almacenamiento del historial de conversación.

    Superficie mínima: solo lo que necesita ConversationService — añadir un
    mensaje y recuperar los últimos N de una sesión.
    """

    @abstractmethod
    async def append_message(
        self,
        session_id: str,
        user_id: int,
        role: str,
        content: str
    ) -> None:
        """
        Guarda un nuevo turno de la conversación.

        Args:
            session_id: ID de sesión generado por el cliente
            user_id: ID del usuario autenticado (scoping, ver adapter)
            role: "user" o "assistant"
            content: Texto del mensaje
        """
        pass

    @abstractmethod
    async def get_recent_messages(
        self,
        session_id: str,
        user_id: int,
        limit: int
    ) -> List[ConversationMessage]:
        """
        Recupera los últimos `limit` mensajes de una sesión, en orden
        cronológico ascendente (el más antiguo primero, listo para
        formatear como historial de prompt).

        Args:
            session_id: ID de sesión a consultar
            user_id: ID del usuario autenticado (scoping, ver adapter)
            limit: Máximo de mensajes a devolver

        Returns:
            List[ConversationMessage]: vacía si la sesión no tiene mensajes
        """
        pass
