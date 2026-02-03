/**
 * Scrollable message list
 */

import { useEffect, useRef } from 'react';
import { MessageItem } from './MessageItem';

export function MessageList({ messages }) {
  const endRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4">
      {messages.map((message) => (
        <MessageItem key={message.id} message={message} />
      ))}
      <div ref={endRef} />
    </div>
  );
}

export default MessageList;
