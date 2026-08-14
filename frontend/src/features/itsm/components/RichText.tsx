/** Minimal rich-text editor for change descriptions. */

import { useEffect, useRef } from 'react';
import { Bold, Italic, List, ListOrdered } from 'lucide-react';

import { cn } from '../lib/cn';

interface RichTextEditorProps {
  value: string;
  onChange: (html: string) => void;
  id?: string;
  invalid?: boolean;
  placeholder?: string;
}

const TOOLS = [
  { cmd: 'bold', label: 'Bold', Icon: Bold },
  { cmd: 'italic', label: 'Italic', Icon: Italic },
  { cmd: 'insertUnorderedList', label: 'Bulleted list', Icon: List },
  { cmd: 'insertOrderedList', label: 'Numbered list', Icon: ListOrdered },
] as const;

export function RichTextEditor({
  value,
  onChange,
  id,
  invalid,
  placeholder,
}: RichTextEditorProps) {
  const ref = useRef<HTMLDivElement>(null);

  // Only write into the DOM when the incoming value genuinely differs, so
  // typing doesn't reset the caret to the start on every keystroke.
  useEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== value) el.innerHTML = value;
  }, [value]);

  function exec(cmd: string) {
    // execCommand is deprecated but remains the only dependency-free way to do
    // inline formatting in a contentEditable. Adequate for this module.
    document.execCommand(cmd);
    ref.current?.focus();
    onChange(ref.current?.innerHTML ?? '');
  }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-md border bg-white',
        invalid ? 'border-red-600' : 'border-slate-300 focus-within:border-sky-500',
      )}
    >
      <div className="flex items-center gap-0.5 border-b border-slate-200 px-1.5 py-1">
        {TOOLS.map(({ cmd, label, Icon }) => (
          <button
            key={cmd}
            type="button"
            onClick={() => exec(cmd)}
            aria-label={label}
            title={label}
            className="rounded p-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            <Icon size={13} />
          </button>
        ))}
      </div>
      <div
        id={id}
        ref={ref}
        role="textbox"
        aria-multiline="true"
        aria-invalid={invalid}
        aria-label={placeholder ?? 'Description'}
        contentEditable
        suppressContentEditableWarning
        onInput={(e) => onChange((e.target as HTMLDivElement).innerHTML)}
        data-placeholder={placeholder}
        className={cn(
          'itsm-richtext min-h-[110px] px-3 py-2 text-[13px] leading-relaxed text-slate-900',
          'focus:outline-none [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5',
        )}
      />
    </div>
  );
}
