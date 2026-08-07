/**
 * Main chat container orchestrating the chat flow
 */

import { useChat } from '../../hooks/useChat';
import { useApp } from '../../hooks/useApp';
import { MessageList } from './MessageList';
import { ChatInput } from './ChatInput';
import { Button } from '../common';
import { llmProviderLabel, vectorDbProviderLabel } from '../../utils/providerLabels';

function EmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-4">📚</div>
        <h2 className="text-xl font-bold text-text-50 mb-2">
          Welcome to Bibliotecario-IA
        </h2>
        <p className="text-text-200 leading-relaxed">
          Ask me questions about the documents you've synced.
          I'll search the knowledge base and give you answers grounded in that content.
        </p>
      </div>
    </div>
  );
}

export function ChatContainer() {
  const { messages, isLoading, sendMessage, clearHistory } = useChat();
  const { health } = useApp();

  const servicesAvailable = health.api && health.llm && health.vectorDb;

  const downServices = [
    !health.llm && llmProviderLabel(health.llmProvider),
    !health.vectorDb && vectorDbProviderLabel(health.vectorDbProvider),
  ].filter(Boolean);

  return (
    <div className="h-full flex flex-col bg-transparent">
      {/* Header with clear button */}
      {messages.length > 0 && (
        <div className="flex justify-end p-2 border-b border-bg-700 bg-bg-850/50 backdrop-blur-sm">
          <Button variant="ghost" size="sm" onClick={clearHistory}>
            Clear chat
          </Button>
        </div>
      )}

      {/* Messages or empty state */}
      {messages.length === 0 ? (
        <EmptyState />
      ) : (
        <MessageList messages={messages} isLoading={isLoading} />
      )}

      {/* Service warning */}
      {!servicesAvailable && (
        <div className="px-4 py-2 bg-error-500/10 border-t border-error-500/30 text-error-400 text-sm">
          ⚠️ Service unavailable: {downServices.join(' and ')}.
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
