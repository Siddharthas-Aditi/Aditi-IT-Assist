# React UI System

## Component Pattern
```tsx
interface Props {
  title: string;
  variant?: 'default' | 'outline';
  onAction: () => void;
}

export function ComponentName({ title, variant = 'default', onAction }: Props) {
  return (
    <div className={cn('base-classes', variantClasses[variant])}>
      <h3>{title}</h3>
      <button onClick={onAction}>Action</button>
    </div>
  );
}
```

## State Management (Zustand)
```tsx
interface ChatStore {
  messages: Message[];
  isLoading: boolean;
  sendMessage: (content: string) => Promise<void>;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  isLoading: false,
  sendMessage: async (content) => {
    set({ isLoading: true });
    // API call
    set({ isLoading: false });
  },
}));
```

## API Layer (React Query)
```tsx
export function useMessages(sessionId: string) {
  return useQuery({
    queryKey: ['messages', sessionId],
    queryFn: () => api.getMessages(sessionId),
  });
}
```

## Layout Pattern
- Sidebar + TopBar + Main content area
- Responsive: sidebar collapses on mobile
- Content area scrolls independently
