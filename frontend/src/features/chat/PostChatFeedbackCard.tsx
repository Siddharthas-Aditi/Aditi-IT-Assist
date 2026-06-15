/**
 * PostChatFeedbackCard
 *
 * 5-step progressive-disclosure survey displayed after a support session
 * transitions to "resolved" or "closed".
 *
 * Steps:
 *   1. Was this helpful? (Yes / No)
 *   2. Was your issue resolved? (Yes / No)
 *   3. Rate your experience (1–5 stars, optional – can skip)
 *   4. Any comments? (free text, optional – can skip)
 *   5. Thank-you confirmation
 *
 * The card is non-intrusive: it can be dismissed and re-accessed
 * from the ticket detail page.
 */

import { useState } from 'react';

import { useSubmitFeedback } from './feedbackApi';

interface Props {
  sessionId: string;
  onDismiss?: () => void;
}

type Step = 1 | 2 | 3 | 4 | 5;

const STARS = [1, 2, 3, 4, 5] as const;

export function PostChatFeedbackCard({ sessionId, onDismiss }: Props) {
  const [step, setStep] = useState<Step>(1);
  const [helpful, setHelpful] = useState<boolean | null>(null);
  const [resolved, setResolved] = useState<boolean | null>(null);
  const [rating, setRating] = useState<number | null>(null);
  const [hoveredRating, setHoveredRating] = useState<number | null>(null);
  const [comment, setComment] = useState('');

  const submitMutation = useSubmitFeedback(sessionId);

  async function handleSubmit() {
    await submitMutation.mutateAsync({
      helpful,
      resolved,
      rating,
      comment: comment.trim() || null,
      feedback_source: 'inline_chat',
    });
    setStep(5);
  }

  function handleSkipToEnd() {
    // Submit whatever we have so far
    void handleSubmit();
  }

  if (step === 5) {
    return (
      <div className="rounded-xl border border-green-200 bg-green-50 p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <span className="text-2xl">✅</span>
          <div>
            <p className="font-semibold text-green-800">Thanks for your feedback!</p>
            <p className="mt-1 text-sm text-green-700">
              Your response helps us improve IT support for everyone at Aditi.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          How did we do?
        </h3>
        <button
          onClick={onDismiss}
          className="text-slate-400 hover:text-slate-600"
          aria-label="Dismiss feedback"
        >
          ✕
        </button>
      </div>

      {/* Step 1 — Helpful? */}
      {step === 1 && (
        <div>
          <p className="mb-3 text-sm text-slate-600">Was this support session helpful?</p>
          <div className="flex gap-3">
            <button
              onClick={() => { setHelpful(true); setStep(2); }}
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 py-2 text-sm font-medium
                         text-slate-700 transition hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700"
            >
              👍 Yes, helpful
            </button>
            <button
              onClick={() => { setHelpful(false); setStep(2); }}
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 py-2 text-sm font-medium
                         text-slate-700 transition hover:border-red-400 hover:bg-red-50 hover:text-red-700"
            >
              👎 Not really
            </button>
          </div>
        </div>
      )}

      {/* Step 2 — Resolved? */}
      {step === 2 && (
        <div>
          <p className="mb-3 text-sm text-slate-600">Was your issue fully resolved?</p>
          <div className="flex gap-3">
            <button
              onClick={() => { setResolved(true); setStep(3); }}
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 py-2 text-sm font-medium
                         text-slate-700 transition hover:border-green-400 hover:bg-green-50 hover:text-green-700"
            >
              ✅ Yes, resolved
            </button>
            <button
              onClick={() => { setResolved(false); setStep(3); }}
              className="flex-1 rounded-lg border border-slate-200 bg-slate-50 py-2 text-sm font-medium
                         text-slate-700 transition hover:border-orange-400 hover:bg-orange-50 hover:text-orange-700"
            >
              ⚠️ Still ongoing
            </button>
          </div>
        </div>
      )}

      {/* Step 3 — Star rating (optional) */}
      {step === 3 && (
        <div>
          <p className="mb-3 text-sm text-slate-600">
            Rate your overall experience{' '}
            <span className="text-xs text-slate-400">(optional)</span>
          </p>
          <div className="mb-4 flex justify-center gap-2">
            {STARS.map((star) => (
              <button
                key={star}
                onMouseEnter={() => setHoveredRating(star)}
                onMouseLeave={() => setHoveredRating(null)}
                onClick={() => setRating(star)}
                className="text-3xl transition-transform hover:scale-110"
                aria-label={`${star} star`}
              >
                {star <= (hoveredRating ?? rating ?? 0) ? '⭐' : '☆'}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setStep(4)}
              disabled={!rating}
              className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-medium text-white
                         transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
            <button
              onClick={() => setStep(4)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-500
                         transition hover:bg-slate-50"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {/* Step 4 — Comment (optional) */}
      {step === 4 && (
        <div>
          <p className="mb-2 text-sm text-slate-600">
            Anything we could improve?{' '}
            <span className="text-xs text-slate-400">(optional)</span>
          </p>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Share any details that might help us improve…"
            rows={3}
            maxLength={2000}
            className="w-full resize-none rounded-lg border border-slate-200 p-3 text-sm text-slate-700
                       placeholder-slate-400 focus:border-blue-400 focus:outline-none focus:ring-1
                       focus:ring-blue-400"
          />
          <div className="mt-3 flex gap-2">
            <button
              onClick={handleSubmit}
              disabled={submitMutation.isPending}
              className="flex-1 rounded-lg bg-blue-600 py-2 text-sm font-medium text-white
                         transition hover:bg-blue-700 disabled:opacity-60"
            >
              {submitMutation.isPending ? 'Submitting…' : 'Submit feedback'}
            </button>
            <button
              onClick={handleSkipToEnd}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-500
                         transition hover:bg-slate-50"
            >
              Skip
            </button>
          </div>
          {submitMutation.isError && (
            <p className="mt-2 text-xs text-red-500">
              Failed to submit — please try again.
            </p>
          )}
        </div>
      )}

      {/* Progress dots */}
      {step < 5 && (
        <div className="mt-4 flex justify-center gap-1.5">
          {([1, 2, 3, 4] as Step[]).map((s) => (
            <span
              key={s}
              className={`h-1.5 w-1.5 rounded-full transition-colors ${
                s === step ? 'bg-blue-500' : s < step ? 'bg-blue-300' : 'bg-slate-200'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
