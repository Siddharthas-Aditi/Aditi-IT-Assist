/** Bulk asset import — upload, preview, then commit. */

import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Download, FileSpreadsheet, Upload } from 'lucide-react';

import { PageHeader } from '../components/chrome';
import { useToast } from '../components/toast-context';
import { Button, EmptyState, Panel, StatusBadge } from '../components/ui';
import { formatMoney } from '../data/money';
import { createAssetsBulk } from '../data/store';
import { cn } from '../lib/cn';
import {
  buildImport,
  detectDelimiter,
  IMPORT_COLUMNS,
  parseDelimited,
  templateCsv,
  type ImportResult,
} from './bulk-import';

const ACCEPTED = '.csv,.tsv,.txt,text/csv,text/tab-separated-values';

function download(filename: string, contents: string, mime = 'text/csv;charset=utf-8;') {
  const blob = new Blob([contents], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function AssetImportPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState('');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [committing, setCommitting] = useState(false);

  async function accept(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;

    if (/\.xlsx?$/i.test(file.name)) {
      toast.error(
        'Excel workbooks are not read directly. In Excel choose File → Save As → CSV, then upload that.',
      );
      return;
    }

    try {
      const text = await file.text();
      const rows = parseDelimited(text, detectDelimiter(text));
      const parsed = buildImport(rows);
      setFileName(file.name);
      setResult(parsed);

      if (parsed.errors.length && parsed.valid.length === 0) {
        toast.error('Nothing in that file could be imported. See the errors below.');
      } else if (parsed.errors.length) {
        toast.info(`${parsed.valid.length} row(s) ready, ${parsed.errors.length} rejected.`);
      } else {
        toast.success(`${parsed.valid.length} row(s) ready to import.`);
      }
    } catch {
      toast.error('That file could not be read as text.');
    }
  }

  function commit() {
    if (!result?.valid.length) return;
    setCommitting(true);
    const created = createAssetsBulk(result.valid);
    setCommitting(false);
    toast.success(`Imported ${created.length} asset${created.length > 1 ? 's' : ''}.`);
    navigate('/itsm/assets');
  }

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Bulk import assets"
        crumbs={[{ label: 'Assets', to: '/itsm/assets' }, { label: 'Import' }]}
        description="Upload a CSV or tab-separated export to create many assets at once."
        actions={
          <Button onClick={() => download('asset-import-template.csv', templateCsv())}>
            <Download size={14} /> Download template
          </Button>
        }
      />

      <Panel title="1. Upload a file">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void accept(e.dataTransfer.files);
          }}
          className={cn(
            'rounded-md border border-dashed px-4 py-8 text-center transition-colors',
            dragging ? 'border-sky-500 bg-sky-50' : 'border-slate-300 bg-slate-50',
          )}
        >
          <FileSpreadsheet size={22} className="mx-auto mb-2 text-slate-400" aria-hidden="true" />
          <p className="text-[13px] text-slate-600">
            Drag a file here or{' '}
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="rounded font-medium text-sky-700 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
            >
              browse
            </button>
          </p>
          <p className="mt-1 text-[11.5px] text-slate-500">
            CSV, TSV, or tab-separated text. Working in Excel? Save as CSV first.
          </p>
          {fileName && (
            <p className="mt-2 text-[12px] font-medium text-slate-700">Loaded: {fileName}</p>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className="sr-only"
            onChange={(e) => {
              void accept(e.target.files);
              e.target.value = '';
            }}
          />
        </div>
      </Panel>

      {result && (
        <>
          <Panel title="2. Review">
            <div className="mb-3 flex flex-wrap gap-4 text-[13px]">
              <span className="text-slate-700">
                <strong className="text-slate-900">{result.totalRows}</strong> data rows
              </span>
              <span className="text-emerald-700">
                <strong>{result.valid.length}</strong> ready
              </span>
              <span className={result.errors.length ? 'text-red-700' : 'text-slate-500'}>
                <strong>{result.errors.length}</strong> rejected
              </span>
              <span className={result.warnings.length ? 'text-amber-700' : 'text-slate-500'}>
                <strong>{result.warnings.length}</strong> warnings
              </span>
            </div>

            {result.errors.length > 0 && (
              <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3">
                <p className="mb-1 flex items-center gap-1.5 text-[12.5px] font-semibold text-red-800">
                  <AlertTriangle size={13} aria-hidden="true" /> Rejected rows
                </p>
                <ul className="space-y-0.5">
                  {result.errors.slice(0, 12).map((e, i) => (
                    <li key={i} className="text-[12px] text-red-800">
                      Row {e.row}: {e.message}
                    </li>
                  ))}
                  {result.errors.length > 12 && (
                    <li className="text-[12px] text-red-700">
                      …and {result.errors.length - 12} more.
                    </li>
                  )}
                </ul>
              </div>
            )}

            {result.warnings.length > 0 && (
              <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 p-3">
                <p className="mb-1 text-[12.5px] font-semibold text-amber-800">
                  Imported with adjustments
                </p>
                <ul className="space-y-0.5">
                  {result.warnings.slice(0, 8).map((w, i) => (
                    <li key={i} className="text-[12px] text-amber-800">
                      Row {w.row}: {w.message}
                    </li>
                  ))}
                  {result.warnings.length > 8 && (
                    <li className="text-[12px] text-amber-700">
                      …and {result.warnings.length - 8} more.
                    </li>
                  )}
                </ul>
              </div>
            )}

            {result.valid.length === 0 ? (
              <EmptyState
                title="No importable rows"
                description="Fix the errors above and upload the file again."
              />
            ) : (
              <div className="overflow-x-auto rounded-md border border-slate-200">
                <table className="w-full text-left">
                  <caption className="sr-only">Rows ready to import</caption>
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      {['Asset Tag', 'Name', 'Type', 'State', 'Cost', 'Location'].map((h) => (
                        <th
                          key={h}
                          scope="col"
                          className="whitespace-nowrap px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.valid.slice(0, 20).map((a) => (
                      <tr key={a.assetTag} className="border-b border-slate-200 last:border-0">
                        <td className="px-3 py-1.5 text-[12.5px] font-medium text-sky-700">
                          {a.assetTag}
                        </td>
                        <td className="px-3 py-1.5 text-[12.5px] text-slate-800">{a.name}</td>
                        <td className="px-3 py-1.5 text-[12.5px] text-slate-600">{a.assetType}</td>
                        <td className="px-3 py-1.5">
                          <StatusBadge status={a.assetState} />
                        </td>
                        <td className="px-3 py-1.5 text-[12.5px] text-slate-800">
                          {formatMoney(a.cost, a.currency)}
                        </td>
                        <td className="px-3 py-1.5 text-[12.5px] text-slate-600">
                          {a.location || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {result.valid.length > 20 && (
                  <p className="border-t border-slate-200 px-3 py-1.5 text-[11.5px] text-slate-500">
                    Showing the first 20 of {result.valid.length} rows.
                  </p>
                )}
              </div>
            )}
          </Panel>

          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              onClick={() => {
                setResult(null);
                setFileName('');
              }}
            >
              Start over
            </Button>
            <Button
              variant="primary"
              onClick={commit}
              disabled={result.valid.length === 0 || committing}
            >
              <Upload size={14} /> Import {result.valid.length} asset
              {result.valid.length === 1 ? '' : 's'}
            </Button>
          </div>
        </>
      )}

      <Panel title="Expected columns">
        <p className="mb-2 text-[12.5px] text-slate-600">
          Column order does not matter and headers are matched case-insensitively. Unrecognised
          columns are ignored.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-200">
                {['Column', 'Required', 'Notes'].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {IMPORT_COLUMNS.map((c) => (
                <tr key={c.header} className="border-b border-slate-200 last:border-0">
                  <td className="whitespace-nowrap px-3 py-1.5 text-[12.5px] font-medium text-slate-800">
                    {c.header}
                  </td>
                  <td className="px-3 py-1.5 text-[12.5px] text-slate-600">
                    {c.required ? 'Yes' : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-[12.5px] text-slate-600">{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
