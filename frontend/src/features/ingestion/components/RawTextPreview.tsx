import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';

interface Props {
  text: string | null | undefined;
  highlightSegment?: string;
  maxHeight?: number;
}

export function RawTextPreview({ text, highlightSegment, maxHeight = 400 }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!text) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed border-gray-200 p-6 text-sm text-gray-400 dark:border-gray-700">
        <FileText className="h-4 w-4" />
        No raw source text available.
      </div>
    );
  }

  // Simple highlight: wrap matching segment in a span
  let display: React.ReactNode = text;
  if (highlightSegment && text.includes(highlightSegment)) {
    const idx = text.indexOf(highlightSegment);
    display = (
      <>
        {text.slice(0, idx)}
        <mark className="rounded bg-yellow-200 px-0.5 dark:bg-yellow-700/40">
          {highlightSegment}
        </mark>
        {text.slice(idx + highlightSegment.length)}
      </>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2 dark:border-gray-700">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          Raw segment text
        </span>
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="flex items-center gap-1 text-xs text-indigo-500 hover:text-indigo-700"
        >
          {expanded ? (
            <>
              <ChevronUp className="h-3 w-3" /> Collapse
            </>
          ) : (
            <>
              <ChevronDown className="h-3 w-3" /> Expand
            </>
          )}
        </button>
      </div>

      {/* Body */}
      <pre
        className={[
          'overflow-x-auto whitespace-pre-wrap break-words p-4 font-mono text-xs text-gray-700 dark:text-gray-300',
          expanded ? '' : `overflow-hidden`,
        ].join(' ')}
        style={expanded ? undefined : { maxHeight }}
      >
        {display}
      </pre>

      {/* Fade overlay when collapsed */}
      {!expanded && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 rounded-b-lg bg-gradient-to-t from-gray-50 dark:from-gray-900" />
      )}
    </div>
  );
}
