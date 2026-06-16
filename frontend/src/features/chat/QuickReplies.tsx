import type { QuickReplyOption } from '../../types';

interface QuickRepliesProps {
  options: QuickReplyOption[];
  onSelect: (value: string) => void;
  disabled?: boolean;
}

/**
 * Quick-reply chips for disambiguation during diagnostic conversations.
 * Displayed below the assistant's clarification question to help users
 * quickly select their specific issue type.
 */
export function QuickReplies({ options, onSelect, disabled }: QuickRepliesProps) {
  return (
    <div className="flex flex-wrap gap-2 mt-3 ml-12">
      {options.map((option) => (
        <button
          key={option.value}
          onClick={() => onSelect(option.label)}
          disabled={disabled}
          className="rounded-full border border-primary/30 bg-primary/5 px-3.5 py-1.5 text-xs font-medium text-primary transition-all hover:bg-primary/15 hover:border-primary/50 hover:shadow-sm active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
