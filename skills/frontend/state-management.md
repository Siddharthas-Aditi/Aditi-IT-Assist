# Skill: State Management

> Zustand + React Query patterns for Aditi IT Assist frontend.

---

## Decision Matrix: Where Does State Go?

| State Type | Tool | Example |
|-----------|------|---------|
| Server data (API responses) | React Query | Chat messages, sessions, KB articles |
| Client-only UI state | Zustand | Sidebar open/closed, active tab |
| Form state | React Hook Form or useState | Input fields, draft messages |
| URL state | React Router | Current page, session ID |
| Ephemeral state | useState | Hover, animation, tooltip |

---

## React Query Patterns

```typescript
// Query keys: hierarchical for invalidation
const queryKeys = {
  sessions: ['sessions'] as const,
  session: (id: string) => ['sessions', id] as const,
  messages: (sessionId: string) => ['sessions', sessionId, 'messages'] as const,
};

// Queries
const { data: sessions } = useQuery({
  queryKey: queryKeys.sessions,
  queryFn: chatApi.getSessions,
});

// Mutations with optimistic updates
const sendMessage = useMutation({
  mutationFn: chatApi.sendMessage,
  onMutate: async (newMessage) => {
    // Optimistically add message to cache
    await queryClient.cancelQueries({ queryKey: queryKeys.messages(sessionId) });
    const previous = queryClient.getQueryData(queryKeys.messages(sessionId));
    queryClient.setQueryData(queryKeys.messages(sessionId), (old) => [...old, newMessage]);
    return { previous };
  },
  onError: (err, variables, context) => {
    // Rollback on error
    queryClient.setQueryData(queryKeys.messages(sessionId), context?.previous);
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.messages(sessionId) });
  },
});
```

---

## Zustand Store Patterns

```typescript
// Small, focused stores — one per domain
// ✅ CORRECT
export const useChatUIStore = create<ChatUIState>((set) => ({
  sidebarOpen: true,
  inputFocused: false,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));

// ❌ WRONG: God store with everything
export const useStore = create((set) => ({
  sessions: [], messages: [], user: null, theme: 'dark', ...  // Too much
}));
```

---

## Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| Store server data in Zustand | Use React Query for server state |
| Create one mega-store | Multiple small stores by domain |
| Fetch in useEffect | Use React Query's `useQuery` |
| Manual cache invalidation | Use `queryClient.invalidateQueries` |
