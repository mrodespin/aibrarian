/**
 * Main chat container orchestrating the chat flow
 */

import { useChat } from '../../hooks/useChat';
import { useApp } from '../../context/AppContext';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Button } from '../common';

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-4">📚</div>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          Bienvenido a Bibliotecario-IA
        </h2>
        <p className="text-gray-600">
          Hazme preguntas sobre los documentos que has sincronizado.
          Buscaré en la base de conocimiento y te daré respuestas basadas en el contenido.
        </p>
      </div>
    </div>
  );
}

export function ChatContainer() {
  const { messages, isLoading, sendMessage, clearHistory } = useChat();
  const { health } = useApp();

  const servicesAvailable = health.ollama && health.chromadb;

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header with clear button */}
      {messages.length > 0 && (
        <div className="flex justify-end p-2 border-b border-gray-200 bg-white">
          <Button variant="ghost" size="sm" onClick={clearHistory}>
            Limpiar chat
          </Button>
        </div>
      )}

      {/* Messages or empty state */}
      {messages.length === 0 ? (
        <EmptyState />
      ) : (
        <MessageList messages={messages} />
      )}

      {/* Service warning */}
      {!servicesAvailable && (
        <div className="px-4 py-2 bg-yellow-50 border-t border-yellow-200 text-yellow-800 text-sm">
          ⚠️ Algunos servicios no están disponibles. Verifica que Ollama y ChromaDB estén corriendo.
        </div>
      )}

      {/* Input */}
      <ChatInput
        onSend={sendMessage}
        isLoading={isLoading}
        disabled={!servicesAvailable}
      />
    </div>
  );
}

export default ChatContainer;
