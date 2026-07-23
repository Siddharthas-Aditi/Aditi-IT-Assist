/**
 * Specialist Available/Away toggle.
 *
 * Loads the caller's current presence on mount and lets them flip it.
 * While `available`, sends a lightweight heartbeat every 20s so the backend
 * can auto-mark stale specialists `away` (offers should only route to
 * specialists actively at their desk).
 */

import { useEffect, useRef, useState } from 'react';

import { queueApi, type Presence } from './api';

const HEARTBEAT_MS = 20000;

export function AvailabilityToggle() {
  const [presence, setPresence] = useState<Presence | null>(null);
  const available = presence?.status === 'available';
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    queueApi
      .getAvailability()
      .then(setPresence)
      .catch(() => {
        /* non-critical — toggle defaults to unknown/away styling */
      });
  }, []);

  useEffect(() => {
    if (!available) {
      if (timer.current) clearInterval(timer.current);
      return;
    }
    timer.current = setInterval(() => {
      queueApi
        .heartbeat()
        .then(setPresence)
        .catch(() => {
          /* non-critical — next interval retries */
        });
    }, HEARTBEAT_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [available]);

  const toggle = async () => {
    const next = available ? 'away' : 'available';
    try {
      setPresence(await queueApi.setAvailability(next));
    } catch {
      /* non-critical — leave presence unchanged, user can retry */
    }
  };

  return (
    <button
      type="button"
      onClick={() => void toggle()}
      className={`px-3 py-1.5 text-xs rounded-full font-medium ${
        available
          ? 'bg-emerald-100 text-emerald-700'
          : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
      }`}
      aria-label={available ? 'Go away' : 'Go available'}
    >
      {available ? '● Available' : '○ Away'}
    </button>
  );
}
