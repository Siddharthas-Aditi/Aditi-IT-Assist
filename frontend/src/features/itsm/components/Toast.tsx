/** Toast feedback for save / submit / workflow actions. */

import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react';

import { cn } from '../lib/cn';
import { ToastContext, type ToastApi, type ToastTone } from './toast-context';

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

const TONES: Record<ToastTone, string> = {
  success: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  error: 'border-red-300 bg-red-50 text-red-800',
  info: 'border-slate-300 bg-white text-slate-800',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const push = useCallback((tone: ToastTone, message: string) => {
    nextId.current += 1;
    const id = nextId.current;
    setToasts((prev) => [...prev, { id, tone, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push('success', m),
      error: (m) => push('error', m),
      info: (m) => push('info', m),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* Assertive so workflow rejections are announced immediately. */}
      <div
        aria-live="assertive"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto rounded-md border px-3 py-2 text-[13px] shadow-lg',
              TONES[t.tone],
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
