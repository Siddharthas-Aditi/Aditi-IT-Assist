import { useRef, useEffect } from 'react';
import { Send, RotateCcw, Sparkles, Bot, Zap, Monitor, Wifi, Key } from 'lucide-react';
import { useState } from 'react';
import { useChatStore } from '../../stores/chat-store';
import { ChatBubble } from './ChatBubble';
import { TypingIndicator } from './TypingIndicator';
import { EscalationBanner } from './EscalationBanner';

const QUICK_PROMPTS = [
  { icon: Monitor, label: 'Outlook not syncing', query: 'My Outlook is not syncing emails' },
  { icon: Wifi, label: 'VPN not connecting', query: 'I cannot connect to the VPN' },
  { icon: Zap, label: 'Zoom audio issues', query: 'My audio is not working in Zoom meetings' },
  { icon: Key, label: 'Account locked', query: 'My account is locked and I cannot log in' },
];

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

  const handleQuickPrompt = async (query: string) => {
    if (isLoading) return;
    setInput('');
    await sendMessage(query);
  };

  const lastMessage = messages[messages.length - 1];
  const showEscalation = lastMessage?.requiresEscalation && lastMessage.role === 'assistant';
  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl gradient-brand shadow-sm">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-foreground">Aditi IT Support</h1>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <p className="text-xs text-muted-foreground">Online · AI-powered</p>
            </div>
          </div>
        </div>
        {!isEmpty && (
          <button
            onClick={reset}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <RotateCcw className="h-3 w-3" />
            New Chat
          </button>
        )}
      </div>

      {/* Messages / Welcome screen */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
        {isEmpty ? (
          /* Welcome state */
          <div className="mx-auto max-w-2xl flex flex-col items-center justify-center h-full gap-6 text-center py-10">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl gradient-brand shadow-lg">
              <Bot className="h-8 w-8 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-foreground mb-1">
                How can I help you today?
              </h2>
              <p className="text-sm text-muted-foreground max-w-sm">
                I'm your Aditi IT Support assistant. Describe your issue or pick a common topic below.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 w-full max-w-sm">
              {QUICK_PROMPTS.map(({ icon: Icon, label, query }) => (
                <button
                  key={label}
                  onClick={() => handleQuickPrompt(query)}
                  disabled={isLoading}
                  className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2.5 text-left text-xs font-medium text-foreground shadow-sm transition-all hover:bg-accent hover:shadow-md disabled:opacity-40"
                >
                  <Icon className="h-3.5 w-3.5 text-primary shrink-0" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl space-y-5">
            {messages.map((message, idx) => (
              <ChatBubble key={message.id} message={message} index={idx} />
            ))}
            {isLoading && <TypingIndicator />}
            {showEscalation && <EscalationBanner />}
          </div>
        )}
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
        <p className="mx-auto mt-2 max-w-2xl text-center text-[10px] text-muted-foreground">
          Responses are AI-generated and grounded in Aditi's internal IT knowledge base
        </p>
      </div>
    </div>
  );
}
