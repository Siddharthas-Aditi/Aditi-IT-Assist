import { describe, expect, it } from 'vitest';

import { HANDOFF_TRIGGER_LABELS, handoffTriggerLabel } from './handoff-labels';

describe('handoff trigger labels', () => {
  it('renders a distinct human-readable label for every persisted trigger', () => {
    for (const [trigger, label] of Object.entries(HANDOFF_TRIGGER_LABELS)) {
      expect(handoffTriggerLabel(trigger as keyof typeof HANDOFF_TRIGGER_LABELS)).toBe(label);
      expect(label).not.toBe(trigger);
    }
  });

  it('does not fabricate a trigger for a legacy handoff without one', () => {
    expect(handoffTriggerLabel(null)).toBeNull();
  });
});
