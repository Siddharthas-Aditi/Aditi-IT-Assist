import { useRef, useEffect } from 'react';
import { Send, RotateCcw, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { useChatStore } from '../../stores/chat-store';
import { ChatBubble } from './ChatBubble';
import { TypingIndicator } from './TypingIndicator';
import { EscalationBanner } from './EscalationBanner';

export function ChatPanel() {
  const { messages, isLoading, sendMessage, reset } = useChatStore();
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const msg = input;
    setInput('');
    await sendMessage(msg);
  };

  const lastMessage = messages[messages.length - 1];
  const showEscalation = lastMessage?.requiresEscalation && lastMessage.role === 'assistant';

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl gradient-brand shadow-sm">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-foreground">IT Support Chat</h1>
            <p className="text-xs text-muted-foreground">AI-powered troubleshooting</p>
          </div>
        </div>
        <button
          onClick={reset}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" />
          New Chat
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
        <div className="mx-auto max-w-2xl space-y-5">
          {messages.map((message, idx) => (
            <ChatBubble key={message.id} message={message} index={idx} />
          ))}
          {isLoading && <TypingIndicator />}
          {showEscalation && <EscalationBanner />}
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border px-5 py-4">
        <div className="mx-auto flex max-w-2xl gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Describe your IT issue..."
            className="flex-1 rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="flex h-[46px] w-[46px] items-center justify-center rounded-xl gradient-brand text-white shadow-md transition-all hover:shadow-lg hover:scale-105 disabled:opacity-40 disabled:hover:scale-100 disabled:hover:shadow-md"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
