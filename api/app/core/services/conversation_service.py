# /api/app/core/services/conversation_service.py
"""
Servicio de Historial de Conversación - TFM Bibliotecario-IA

Persiste y recupera los turnos de una conversación, y los formatea como un
bloque de texto listo para inyectar en el prompt del LLM (ver
RAGService.ask_question / OllamaAdapter.generate_response).

Deliberadamente NO vive dentro de RAGService: RAGService está documentado
como necesitando exactamente 2 puertos (LLM + VectorDB) — añadir un tercero
rompería ese contrato y todos los sitios que instancian
RAGService(llm=..., vector_db=...) (incluidos los tests de integración).
En su lugar, el endpoint /ask (main.py) compone ambos servicios: pide el
historial antes de llamar a rag_service.ask_question(), y persiste los
nuevos turnos después — mismo patrón "endpoints finos que orquestan
servicios" que ya usa el resto de main.py.

Equivalente en TypeScript:
    class ConversationService {
        constructor(private conversationRepository: ConversationRepositoryPort) {}
        async appendTurn(sessionId, userId, question, answer): Promise<void> { ... }
        async getHistoryPromptBlock(sessionId, userId): Promise<string> { ... }
    }
"""

from app.core.ports.conversation_repository_port import ConversationRepositoryPort
from app.config.settings import settings
from app.core.observability import get_logger

logger = get_logger(__name__)


class ConversationService:
    """
    Servicio de historial de conversación: persiste turnos y los formatea
    como contexto para el prompt del LLM.

    Solo necesita un puerto (ConversationRepositoryPort), mismo patrón que
    AuthService con UserRepositoryPort.
    """

    def __init__(self, conversation_repository: ConversationRepositoryPort):
        self.conversation_repository = conversation_repository

    async def append_turn(
        self,
        session_id: str,
        user_id: int,
        question: str,
        answer: str
    ) -> None:
        """
        Guarda un turno completo (pregunta del usuario + respuesta del
        asistente) del historial.

        Args:
            session_id: ID de sesión generado por el cliente
            user_id: ID del usuario autenticado
            question: Pregunta del usuario
            answer: Respuesta generada (incluye el caso de error — ver
                    docstring del endpoint /ask en main.py)
        """
        await self.conversation_repository.append_message(session_id, user_id, "user", question)
        await self.conversation_repository.append_message(session_id, user_id, "assistant", answer)

    async def get_history_prompt_block(self, session_id: str, user_id: int) -> str:
        """
        Recupera los últimos turnos de la conversación y los formatea como
        texto, listo para prepender al prompt del LLM.

        Formato (mismo estilo que RAGService._build_context para las
        fuentes, por consistencia):
            Usuario: ¿Qué es RAG?
            Asistente: RAG combina búsqueda con generación de texto...

            Usuario: ¿puedes explicarlo con un ejemplo?
            Asistente: ...

        Args:
            session_id: ID de sesión a consultar
            user_id: ID del usuario autenticado

        Returns:
            str: bloque de historial formateado, cadena vacía si no hay
                 turnos previos (settings.conversation_history_turns=0
                 también produce cadena vacía, sin consultar la BD)
        """
        if settings.conversation_history_turns <= 0:
            return ""

        # N turnos = N mensajes de usuario + N de asistente
        limit = settings.conversation_history_turns * 2
        messages = await self.conversation_repository.get_recent_messages(session_id, user_id, limit)

        if not messages:
            return ""

        lines = []
        for message in messages:
            speaker = "Usuario" if message.role == "user" else "Asistente"
            lines.append(f"{speaker}: {message.content}")

        return "\n\n".join(lines)
