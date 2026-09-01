import type { HandoffTrigger } from './api';

export const HANDOFF_TRIGGER_LABELS: Record<HandoffTrigger, string> = {
  user_request: 'User requested a specialist',
  max_turns: 'Maximum troubleshooting turns reached',
  unclassifiable_issue: 'Issue could not be classified safely',
  no_grounded_articles: 'No approved grounded article was available',
  low_retrieval_confidence: 'Retrieval confidence was too low',
  failed_step_threshold: 'Multiple troubleshooting steps failed',
  grounded_steps_exhausted: 'Grounded troubleshooting steps were exhausted',
  low_resolution_confidence: 'Resolution confidence was too low',
  delegation_cap: 'Specialist delegation limit was reached',
  loop_detected: 'Loop detection guardrail fired',
  policy_block: 'Policy guardrail blocked further automation',
  other: 'Other escalation safeguard',
};

export function handoffTriggerLabel(trigger: HandoffTrigger | null | undefined): string | null {
  return trigger ? HANDOFF_TRIGGER_LABELS[trigger] : null;
}
