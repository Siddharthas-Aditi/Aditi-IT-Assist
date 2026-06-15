/**
 * ExtractionMetaBanner — shows v2 pipeline metadata for a candidate.
 *
 * Displayed at the top of CandidateEditorPage when schema_version "2.0.0"
 * is present. Shows: parser profile, confidence level, review_required flag,
 * parser warnings, and optionally per-field confidence scores.
 */
import { AlertTriangle, ChevronDown, ChevronUp, Info } from 'lucide-react';
import { useState } from 'react';

import type { ConfidenceLevel, IngestionCandidateDetail } from '@/types/ingestion';
import { ConfidenceBadge } from './ConfidenceBadge';

interface Props {
  candidate: IngestionCandidateDetail;
}

const FIELD_LABEL: Record<string, string> = {
  title: 'Title',
  category: 'Category',
  short_summary: 'Summary',
  symptoms: 'Symptoms',
  troubleshooting_steps: 'Troubleshooting',
  resolution_steps: 'Resolution',
  escalation_criteria: 'Escalation',
  tags: 'Tags',
  product_or_system: 'Product',
};

export function ExtractionMetaBanner({ candidate }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!candidate.schema_version) return null;

  const warnings = candidate.parser_warnings ?? [];
  const fieldConf = candidate.field_confidences ?? {};
  const reviewRequired = candidate.review_required;

  return (
    <div
      className={[
        'mb-4 rounded-lg border px-4 py-3',
        reviewRequired
          ? 'border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/20'
          : 'border-blue-100 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/20',
      ].join(' ')}
    >
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        {reviewRequired ? (
          <span className="flex items-center gap-1 font-semibold text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5" />
            Review required
          </span>
        ) : (
          <span className="flex items-center gap-1 font-semibold text-blue-700 dark:text-blue-400">
            <Info className="h-3.5 w-3.5" />
            Extraction info
          </span>
        )}

        <ConfidenceBadge
          score={candidate.extracted_confidence ?? undefined}
          level={candidate.confidence_level as ConfidenceLevel | null}
          size="sm"
        />

        {candidate.parser_profile && (
          <span className="text-gray-500 dark:text-gray-400">
            Profile: <span className="font-medium text-gray-700 dark:text-gray-300">{candidate.parser_profile}</span>
          </span>
        )}

        {candidate.schema_version && (
          <span className="text-gray-400 dark:text-gray-500">
            Schema v{candidate.schema_version}
          </span>
        )}

        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="ml-auto flex items-center gap-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          {expanded ? 'Hide details' : 'Show details'}
        </button>
      </div>

      {/* Expanded: parser warnings + field confidences */}
      {expanded && (
        <div className="mt-3 space-y-3">
          {warnings.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-medium text-gray-600 dark:text-gray-400">
                Extraction warnings:
              </p>
              <ul className="space-y-1">
                {warnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                    <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(fieldConf).length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-gray-600 dark:text-gray-400">
                Per-field confidence:
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(fieldConf).map(([field, conf]) => (
                  <div key={field} className="flex items-center gap-1.5 text-xs">
                    <span className="text-gray-500 dark:text-gray-400">
                      {FIELD_LABEL[field] ?? field}:
                    </span>
                    <ConfidenceBadge score={conf} showLabel={false} size="sm" />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
