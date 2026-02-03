/**
 * Scrollable message list
 */

import { useEffect, useRef } from 'react';
import { MessageItem } from './MessageItem';

function SkeletonMessage() {
  return (
    <div className="flex justify-start mb-6 animate-fade-in">
      <div className="max-w-[85%] md:max-w-[70%] rounded-2xl px-5 py-4 bg-bg-850 border border-bg-700 shadow-sm">
        <div className="space-y-3">
          <div className="h-4 bg-bg-800 rounded animate-pulse w-3/4" />
          <div className="h-4 bg-bg-800 rounded animate-pulse w-full" />
          <div className="h-4 bg-bg-800 rounded animate-pulse w-5/6" />
        </div>
      </div>
    </div>
  );
}

export function MessageList({ messages, isLoading }) {
  const endRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      {isLoading && <SkeletonMessage />}
      <div ref={endRef} />
    </div>
  );
}

export default MessageList;
