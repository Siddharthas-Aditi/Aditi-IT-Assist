import { useCallback, useRef, useState } from 'react';
import { Upload, FileText, AlertCircle } from 'lucide-react';

const ALLOWED = ['docx', 'pdf', 'pptx', 'txt', 'md'];
const MAX_MB = 50;

interface Props {
  onFileSelected: (file: File) => void;
  isUploading?: boolean;
}

function getExt(name: string): string {
  return name.split('.').pop()?.toLowerCase() ?? '';
}

export function DropZone({ onFileSelected, isUploading = false }: Props) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validate = (file: File): string | null => {
    const ext = getExt(file.name);
    if (!ALLOWED.includes(ext)) {
      return `Unsupported type ".${ext}". Allowed: ${ALLOWED.join(', ')}`;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      return `File exceeds ${MAX_MB} MB limit.`;
    }
    return null;
  };

  const handleFile = useCallback(
    (file: File) => {
      const err = validate(file);
      if (err) {
        setError(err);
        return;
      }
      setError(null);
      onFileSelected(file);
    },
    [onFileSelected],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // Reset so the same file can be re-selected
    e.target.value = '';
  };

  return (
    <div className="space-y-2">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload document"
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        className={[
          'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 cursor-pointer',
          'transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500',
          isDragging
            ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-950/30'
            : 'border-gray-300 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800',
          isUploading ? 'pointer-events-none opacity-60' : '',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".docx,.pdf,.pptx,.txt,.md"
          className="hidden"
          onChange={onInputChange}
          disabled={isUploading}
        />
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900">
          {isUploading ? (
            <Upload className="h-7 w-7 animate-pulse text-indigo-500" />
          ) : (
            <FileText className="h-7 w-7 text-indigo-500" />
          )}
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {isUploading ? 'Uploading…' : 'Drop a file here or click to browse'}
          </p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            DOCX, PDF, PPTX, TXT, MD — max {MAX_MB} MB
          </p>
        </div>
      </div>
      {error && (
        <div className="flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
}
