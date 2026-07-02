/**
 * ConsentWatcher — employee-side remote-support consent surfacing.
 *
 * Mounted once in EmployeeLayout so a pending consent request reaches the
 * employee anywhere in the workspace (support chat, live chat, tickets).
 * Polls `GET /remote-support/consent/pending` and renders the ConsentModal
 * when a specialist has requested a session. Grant/deny is a one-shot
 * decision recorded immutably server-side; nothing is ever shared before
 * an explicit grant.
 */

import { useCallback, useEffect, useState } from 'react';

import { ConsentModal } from '@/components/remote-support/ConsentModal';
import { remoteApi } from '@/lib/api';
import type { ConsentNotification } from '@/types/remote-support';

const CONSENT_POLL_INTERVAL_MS = 5000;

export function ConsentWatcher() {
  const [notification, setNotification] = useState<ConsentNotification | null>(null);
  // Session ids the user already responded to (or dismissed) this page-load —
  // never re-show a modal for the same request.
  const [handled, setHandled] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await remoteApi.pendingConsent();
        if (cancelled) return;
        if (res.pending && res.notification && !handled.has(res.notification.session_id)) {
          setNotification(res.notification);
        } else if (!res.pending) {
          setNotification(null);
        }
      } catch {
        // Best-effort polling: the in-chat system message is the fallback signal.
      }
    };
    void check();
    const t = window.setInterval(() => void check(), CONSENT_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [handled]);

  const markHandled = useCallback((sessionId: string) => {
    setHandled((prev) => new Set(prev).add(sessionId));
    setNotification(null);
  }, []);

  if (!notification) return null;

  return (
    <ConsentModal
      notification={notification}
      onGrant={async () => {
        await remoteApi.respondConsent(notification.session_id, true);
        markHandled(notification.session_id);
      }}
      onDeny={async (reason?: string) => {
        await remoteApi.respondConsent(notification.session_id, false, reason);
        markHandled(notification.session_id);
      }}
      onClose={() => markHandled(notification.session_id)}
    />
  );
}
