# Skill: React Component Architecture

> Frontend component patterns for Aditi IT Assist.

---

## Pattern 1: Component Structure

```typescript
// ✅ Single-responsibility, typed props, hooks-based
interface ChatMessageProps {
  message: ChatMessage;
  isLatest?: boolean;
  onRetry?: (messageId: string) => void;
}

export function ChatMessage({ message, isLatest = false, onRetry }: ChatMessageProps) {
  const formattedTime = useFormattedTime(message.timestamp);

  return (
    <div className={cn(
      "flex gap-3 p-4 rounded-lg",
      message.role === "user" ? "bg-muted" : "bg-card"
    )}>
      <Avatar role={message.role} />
      <div className="flex-1 space-y-2">
        <p className="text-sm">{message.content}</p>
        <span className="text-xs text-muted-foreground">{formattedTime}</span>
      </div>
    </div>
  );
}
```

---

## Pattern 2: Feature Organization

```
src/
├── components/        # Shared UI components (Button, Card, etc.)
│   └── ui/           # shadcn/ui components
├── features/         # Feature modules (self-contained)
│   └── chat/
│       ├── ChatContainer.tsx    # Feature root
│       ├── ChatInput.tsx        # Input area
│       ├── ChatMessage.tsx      # Single message
│       ├── ChatMessageList.tsx  # Message list
│       └── use-chat.ts          # Feature hook
├── pages/            # Route-level pages
│   └── ChatPage.tsx  # Composes features
├── lib/              # Utilities (api, cn, etc.)
├── store/            # Zustand stores
└── types/            # Shared type definitions
```

---

## Pattern 3: Data Fetching (React Query)

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { chatApi } from '@/lib/api';

export function useChat(sessionId: string) {
  const queryClient = useQueryClient();

  const messagesQuery = useQuery({
    queryKey: ['chat', sessionId, 'messages'],
    queryFn: () => chatApi.getSession(sessionId),
    refetchInterval: 5000, // Poll for updates
  });

  const sendMutation = useMutation({
    mutationFn: (message: string) => chatApi.sendMessage(message, sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat', sessionId] });
    },
  });

  return {
    messages: messagesQuery.data?.messages ?? [],
    isLoading: messagesQuery.isLoading,
    send: sendMutation.mutate,
    isSending: sendMutation.isPending,
  };
}
```

---

## Pattern 4: State Management (Zustand)

```typescript
import { create } from 'zustand';

interface ChatStore {
  activeSessionId: string | null;
  isSidebarOpen: boolean;
  setActiveSession: (id: string) => void;
  toggleSidebar: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  activeSessionId: null,
  isSidebarOpen: true,
  setActiveSession: (id) => set({ activeSessionId: id }),
  toggleSidebar: () => set((s) => ({ isSidebarOpen: !s.isSidebarOpen })),
}));
```

**Rules**:
- Server state → React Query (not Zustand)
- Client-only UI state → Zustand
- Keep stores small and focused (one per domain)

---

## Pattern 5: Error Boundaries

```typescript
import { ErrorBoundary } from 'react-error-boundary';

function ChatErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  return (
    <div className="p-4 text-center">
      <p className="text-destructive">Something went wrong with the chat.</p>
      <Button onClick={resetErrorBoundary}>Try Again</Button>
    </div>
  );
}

// In page:
<ErrorBoundary FallbackComponent={ChatErrorFallback}>
  <ChatContainer />
</ErrorBoundary>
```

---

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| `any` types | Define proper interfaces |
| Fetch in components directly | Use React Query hooks |
| Giant god components | Split into focused components |
| Inline styles | Use Tailwind utility classes |
| Props drilling 3+ levels | Use Zustand or Context |
| `useEffect` for data fetching | Use React Query |
