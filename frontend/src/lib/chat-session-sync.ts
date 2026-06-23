/**
 * Cross-tab chat session synchronization.
 *
 * Persists the active support chat's messages, sessionId, and waiting state
 * to localStorage so that:
 *   - Opening a new tab shows the same conversation in progress
 *   - Refreshing recovers the chat transcript
 *   - Chat state is cleared on logout (via the auth store)
 *
 * The storage key is scoped per-user (by userId) so switching accounts
 * doesn't leak chat history from a different user.
 *
 * This is a thin helper — it does NOT replace the component-level useState;
 * instead it snapshots state to localStorage on every change and provides
 * a restore function for initial load.
 */

const STORAGE_KEY_PREFIX = 'aditi-chat-session';

interface SerializedChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  requiresEscalation?: boolean;
  escalationOffered?: boolean;
  ticket?: {
    ticket_id: string;
    ticket_number: string;
    status: string;
    priority: string;
    live_agent_requested: boolean;
  };
  resolutionSteps?: { step_number: number; instruction: string; details?: string }[];
  followUpQuestion?: string;
  category?: string;
  confidence?: number;
  isError?: boolean;
}

interface ChatSessionSnapshot {
  sessionId: string | null;
  messages: SerializedChatMessage[];
  waitingForSpecialist: boolean;
  teamsNotified: boolean;
  savedAt: number; // epoch ms
}

function storageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}:${userId}`;
}

/**
 * Save the current chat state to localStorage.
 * Call this after every state change (new message, session change, etc.).
 */
export function saveChatSession(
  userId: string,
  state: {
    sessionId: string | null;
    messages: SerializedChatMessage[];
    waitingForSpecialist: boolean;
    teamsNotified: boolean;
  },
): void {
  try {
    const snapshot: ChatSessionSnapshot = {
      ...state,
      savedAt: Date.now(),
    };
    localStorage.setItem(storageKey(userId), JSON.stringify(snapshot));
  } catch {
    // localStorage full or unavailable — degrade silently.
  }
}

/**
 * Restore a previously saved chat session.
 * Returns null if no saved state exists or the state is stale (> 24 hours).
 */
export function restoreChatSession(
  userId: string,
): ChatSessionSnapshot | null {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return null;

    const snapshot = JSON.parse(raw) as ChatSessionSnapshot;

    // Discard sessions older than 24 hours — they're stale.
    const MAX_AGE_MS = 24 * 60 * 60 * 1000;
    if (Date.now() - snapshot.savedAt > MAX_AGE_MS) {
      localStorage.removeItem(storageKey(userId));
      return null;
    }

    return snapshot;
  } catch {
    return null;
  }
}

/** Clear the persisted chat session (e.g. on logout or explicit reset). */
export function clearChatSession(userId: string): void {
  try {
    localStorage.removeItem(storageKey(userId));
  } catch {
    // Ignore
  }
}

/** Clear ALL chat sessions (for logout where userId may be unknown). */
export function clearAllChatSessions(): void {
  try {
    const keys = Object.keys(localStorage);
    for (const key of keys) {
      if (key.startsWith(STORAGE_KEY_PREFIX)) {
        localStorage.removeItem(key);
      }
    }
  } catch {
    // Ignore
  }
}
