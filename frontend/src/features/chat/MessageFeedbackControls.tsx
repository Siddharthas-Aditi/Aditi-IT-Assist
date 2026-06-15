/**
 * MessageFeedbackControls
 *
 * Inline thumbs-up / thumbs-down controls displayed below individual AI
 * assistant messages in the chat interface.  On thumbs-down an optional
 * comment field expands to allow the user to add context.
 */

import { useState } from 'react';

import { useSubmitMessageFeedback } from './feedbackApi';

interface Props {
  messageId: string;
  sessionId: string;
  /** Pre-populated initial vote if feedback already exists */
  initialHelpful?: boolean | null;
}

export function MessageFeedbackControls({ messageId, sessionId, initialHelpful }: Props) {
  const [vote, setVote] = useState<boolean | null>(initialHelpful ?? null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState('');

  const submitMutation = useSubmitMessageFeedback(messageId, sessionId);

  async function submit(helpful: boolean, commentText?: string) {
    await submitMutation.mutateAsync({
      helpful,
      comment: commentText?.trim() || null,
    });
    setVote(helpful);
    if (!helpful && !commentText) {
      setShowComment(true);
    } else {
      setShowComment(false);
    }
  }

  async function submitComment() {
    if (vote !== null) {
      await submit(vote, comment);
    }
  }

  return (
    <div className="mt-1 flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-400">Was this helpful?</span>

        {/* Thumbs up */}
        <button
          onClick={() => void submit(true)}
          disabled={submitMutation.isPending}
          aria-label="Thumbs up"
          className={`rounded p-0.5 text-base transition hover:bg-green-100 ${
            vote === true ? 'text-green-600' : 'text-slate-400 hover:text-green-600'
          }`}
        >
          👍
        </button>

        {/* Thumbs down */}
        <button
          onClick={() => void submit(false)}
          disabled={submitMutation.isPending}
          aria-label="Thumbs down"
          className={`rounded p-0.5 text-base transition hover:bg-red-100 ${
            vote === false ? 'text-red-500' : 'text-slate-400 hover:text-red-500'
          }`}
        >
          👎
        </button>

        {submitMutation.isPending && (
          <span className="text-xs text-slate-400">Saving…</span>
        )}
      </div>

      {/* Optional comment on thumbs-down */}
      {showComment && vote === false && (
        <div className="ml-0 flex gap-2">
          <input
            type="text"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What went wrong? (optional)"
            maxLength={500}
            className="flex-1 rounded border border-slate-200 px-2 py-1 text-xs text-slate-700
                       placeholder-slate-400 focus:border-red-300 focus:outline-none focus:ring-1
                       focus:ring-red-300"
          />
          <button
            onClick={() => void submitComment()}
            disabled={submitMutation.isPending}
            className="rounded bg-slate-700 px-2 py-1 text-xs text-white transition hover:bg-slate-800
                       disabled:opacity-50"
          >
            Send
          </button>
          <button
            onClick={() => setShowComment(false)}
            className="rounded px-1 py-1 text-xs text-slate-400 hover:text-slate-600"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  );
}
