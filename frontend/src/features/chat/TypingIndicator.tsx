import { Bot } from 'lucide-react';

export function TypingIndicator() {
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl gradient-brand shadow-sm">
        <Bot className="h-4 w-4 text-white animate-pulse" />
      </div>
      <div className="rounded-2xl rounded-bl-md bg-card border border-border px-4 py-3 shadow-sm">
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 animate-bounce rounded-full bg-primary/60" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-primary/60 [animation-delay:150ms]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-primary/60 [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}
