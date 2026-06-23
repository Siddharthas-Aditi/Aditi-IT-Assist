import { describe, expect, it } from 'vitest';

import {
  notifyDesktop,
  playNotificationChime,
  requestNotificationPermission,
} from './notification-sound';

// jsdom provides no AudioContext / Notification, so these must degrade to
// silent no-ops rather than throwing — that's the contract the polling loop
// relies on (it fires the chime on every new handoff without try/catch).
describe('notification-sound', () => {
  it('playNotificationChime is a no-op without AudioContext', () => {
    expect(() => playNotificationChime()).not.toThrow();
  });

  it('notifyDesktop is a no-op without Notification', () => {
    expect(() => notifyDesktop('title', 'body')).not.toThrow();
  });

  it('requestNotificationPermission is a no-op without Notification', () => {
    expect(() => requestNotificationPermission()).not.toThrow();
  });
});
