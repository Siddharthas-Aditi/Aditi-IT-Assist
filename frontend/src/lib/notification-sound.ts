/**
 * Lightweight notification chime for new live-support handoffs.
 *
 * Uses the Web Audio API to synthesize a short two-tone beep — no audio asset
 * to ship or 404. Browsers gate audio behind a user gesture, so the
 * AudioContext is created lazily and `resume()`d on demand; if the browser
 * still refuses (no prior interaction), the call fails silently rather than
 * throwing. Callers debounce *what* counts as "new" (see the queue page); this
 * module only knows how to make the sound.
 */

let ctx: AudioContext | null = null;

function getContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Ctor =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!ctx) ctx = new Ctor();
  return ctx;
}

/** Play a short attention chime. Safe to call from a polling loop. */
export function playNotificationChime(): void {
  const audio = getContext();
  if (!audio) return;
  // Resume in case the context is suspended (autoplay policy).
  void audio.resume().catch(() => {});
  const now = audio.currentTime;
  // Two quick ascending tones — distinct from OS/error sounds.
  for (const [i, freq] of [880, 1175].entries()) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    const start = now + i * 0.16;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.18, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.15);
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start(start);
    osc.stop(start + 0.16);
  }
}

/** Best-effort desktop notification (no-op without permission). */
export function notifyDesktop(title: string, body: string): void {
  if (typeof Notification === 'undefined') return;
  if (Notification.permission === 'granted') {
    try {
      new Notification(title, { body });
    } catch {
      /* some browsers throw outside a SW context — ignore */
    }
  }
}

/** Ask once for desktop-notification permission (call from a click handler). */
export function requestNotificationPermission(): void {
  if (typeof Notification === 'undefined') return;
  if (Notification.permission === 'default') {
    void Notification.requestPermission().catch(() => {});
  }
}
