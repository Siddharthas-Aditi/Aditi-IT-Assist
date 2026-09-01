import { CheckCircle2, XCircle } from "lucide-react";

import {
  buildTroubleshootingHistory,
  type TroubleshootingMessage,
} from "./troubleshooting-history";

export function TroubleshootingHistory({ messages }: { messages: TroubleshootingMessage[] }) {
  const history = buildTroubleshootingHistory(messages);
  if (!history.length) return null;

  return (
    <section aria-label="Troubleshooting history" className="border-t border-gray-100 bg-slate-50 px-4 py-3 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Troubleshooting history</p>
        <ul className="mt-2 space-y-1">
          {history.map((step) => {
            const failed = step.outcome === "failed";
            return (
              <li key={step.key} className="flex items-start gap-2 text-xs text-slate-700">
                {failed ? <XCircle aria-hidden="true" size={14} className="mt-0.5 shrink-0 text-red-600" /> : <CheckCircle2 aria-hidden="true" size={14} className="mt-0.5 shrink-0 text-indigo-600" />}
                <span>{step.instruction}</span>
                <span className={failed ? "font-medium text-red-700" : "text-slate-500"}>{failed ? "Failed" : "Suggested"}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
