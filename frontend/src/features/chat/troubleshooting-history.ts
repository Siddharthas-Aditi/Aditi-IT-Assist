export interface TroubleshootingMessage {
  role: "user" | "assistant";
  content: string;
  resolutionSteps?: { step_number: number; instruction: string }[];
}

export interface TroubleshootingHistoryEntry {
  key: string;
  instruction: string;
  outcome: "suggested" | "failed";
}

const FAILURE_REPLY = /\b(still not working|did(?: not|n't) work|failed|no change)\b/i;

/** Derive the visible current-conversation history without exposing debug data. */
export function buildTroubleshootingHistory(
  messages: TroubleshootingMessage[],
): TroubleshootingHistoryEntry[] {
  const history: TroubleshootingHistoryEntry[] = [];
  let lastSuggested: number[] = [];

  for (const message of messages) {
    if (message.role === "assistant" && message.resolutionSteps?.length) {
      lastSuggested = message.resolutionSteps.map((step) => {
        history.push({
          key: `${history.length}-${step.step_number}`,
          instruction: step.instruction,
          outcome: "suggested",
        });
        return history.length - 1;
      });
    } else if (message.role === "user" && FAILURE_REPLY.test(message.content)) {
      for (const index of lastSuggested) history[index].outcome = "failed";
      lastSuggested = [];
    }
  }

  return history;
}
