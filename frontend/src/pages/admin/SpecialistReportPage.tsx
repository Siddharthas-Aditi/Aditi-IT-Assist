/**
 * Per-specialist report — table + charts + CSV/Excel/PDF export.
 *
 * Defaults to the current calendar month; the lead/admin can widen or narrow
 * the range with the date pickers. Mirrors the DashboardPage look (PageHeader,
 * Card, loading/error/empty states) so the two analytics screens feel like one
 * system.
 */

import { useMemo, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { PageHeader } from '@/components/admin';
import { Card } from '@/components/ui';
import { downloadSpecialistReport, useSpecialistReport } from '@/features/admin/api';
import type { SpecialistReportRow } from '@/features/admin/types';

/** Token rendered for a null/missing numeric cell — a single em-dash. */
const EMPTY = '—';

type ExportFormat = 'csv' | 'xlsx' | 'pdf';

const EXPORT_OPTIONS: { format: ExportFormat; label: string }[] = [
  { format: 'csv', label: 'CSV' },
  { format: 'xlsx', label: 'Excel' },
  { format: 'pdf', label: 'PDF' },
];

/** First and last day (inclusive) of the current calendar month, as `YYYY-MM-DD`. */
function currentMonthRange(): { start: string; end: string } {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return { start: toDateInputValue(first), end: toDateInputValue(last) };
}

function toDateInputValue(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Renders a nullable number as a fixed-precision string, or the empty token. */
function numOrDash(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return EMPTY;
  return digits > 0 ? value.toFixed(digits) : String(value);
}

export function SpecialistReportPage() {
  const defaults = useMemo(() => currentMonthRange(), []);
  const [start, setStart] = useState(defaults.start);
  const [end, setEnd] = useState(defaults.end);
  const [downloading, setDownloading] = useState<ExportFormat | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch, isFetching } = useSpecialistReport(start, end);

  const rows = data?.rows ?? [];
  const hasData = rows.length > 0;

  const chartData = rows.map((row) => ({
    name: row.agent_name,
    tickets: row.total_tickets,
    slaViolations: row.sla_violations,
  }));

  // Agents with no resolved tickets in range have `avg_resolution_hours: null`
  // ("No data") — plotting a 0-hour bar for them would misleadingly read as
  // an instant resolution, so they're skipped from this chart entirely
  // rather than coerced to 0.
  const resolutionChartData = rows
    .filter((row) => row.avg_resolution_hours != null)
    .map((row) => ({
      name: row.agent_name,
      avgResolutionHours: row.avg_resolution_hours as number,
    }));

  async function handleDownload(format: ExportFormat) {
    setDownloadError(null);
    setDownloading(format);
    try {
      await downloadSpecialistReport(start, end, format);
    } catch {
      setDownloadError(`Failed to download the ${format.toUpperCase()} report. Please try again.`);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Specialist Report"
        description="Per-agent ticket, SLA, and satisfaction performance"
        breadcrumbs={[{ label: 'Analytics', to: '/dashboard' }, { label: 'Specialist Report' }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              From
              <input
                type="date"
                value={start}
                max={end}
                onChange={(e) => setStart(e.target.value)}
                className="rounded-lg border border-border bg-card px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              To
              <input
                type="date"
                value={end}
                min={start}
                onChange={(e) => setEnd(e.target.value)}
                className="rounded-lg border border-border bg-card px-2 py-1 text-sm text-foreground"
              />
            </label>
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        }
      />

      <div className="p-6">
        {isLoading ? (
          <div className="py-16 text-center text-muted-foreground">Loading specialist report…</div>
        ) : isError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 py-12 text-center text-sm text-destructive">
            Failed to load the specialist report. Please refresh.
          </div>
        ) : (
          <>
            {/* Downloads */}
            <div className="mb-6 flex flex-wrap items-center gap-2">
              {EXPORT_OPTIONS.map((opt) => (
                <button
                  key={opt.format}
                  type="button"
                  disabled={downloading !== null}
                  onClick={() => handleDownload(opt.format)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-60"
                >
                  <Download size={14} />
                  {downloading === opt.format ? `Downloading ${opt.label}…` : opt.label}
                </button>
              ))}
              {downloadError && <p className="text-sm text-destructive">{downloadError}</p>}
            </div>

            {!hasData ? (
              <Card>
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No specialist activity in this period.
                </p>
              </Card>
            ) : (
              <>
                {/* Charts */}
                <div className="mb-6 grid gap-6 lg:grid-cols-3">
                  <Card>
                    <h3 className="mb-4 text-sm font-semibold text-foreground">
                      Tickets per agent
                    </h3>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(0 0% 90%)" />
                          <XAxis
                            dataKey="name"
                            tick={{ fontSize: 12 }}
                            interval={0}
                            angle={-20}
                            textAnchor="end"
                            height={50}
                          />
                          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                          <Tooltip />
                          <Bar dataKey="tickets" name="Total tickets" fill="hsl(211 84% 12%)" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </Card>

                  <Card>
                    <h3 className="mb-4 text-sm font-semibold text-foreground">
                      Avg resolution time per agent (hrs)
                    </h3>
                    <div className="h-64">
                      {resolutionChartData.length === 0 ? (
                        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                          No data
                        </div>
                      ) : (
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={resolutionChartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(0 0% 90%)" />
                            <XAxis
                              dataKey="name"
                              tick={{ fontSize: 12 }}
                              interval={0}
                              angle={-20}
                              textAnchor="end"
                              height={50}
                            />
                            <YAxis allowDecimals tick={{ fontSize: 12 }} />
                            <Tooltip />
                            <Bar
                              dataKey="avgResolutionHours"
                              name="Avg resolution (hrs)"
                              fill="hsl(211 60% 45%)"
                              radius={[4, 4, 0, 0]}
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      )}
                    </div>
                  </Card>

                  <Card>
                    <h3 className="mb-4 text-sm font-semibold text-foreground">
                      SLA violations per agent
                    </h3>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(0 0% 90%)" />
                          <XAxis
                            dataKey="name"
                            tick={{ fontSize: 12 }}
                            interval={0}
                            angle={-20}
                            textAnchor="end"
                            height={50}
                          />
                          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                          <Tooltip />
                          <Bar
                            dataKey="slaViolations"
                            name="SLA violations"
                            fill="hsl(0 84% 60%)"
                            radius={[4, 4, 0, 0]}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </Card>
                </div>

                {/* Table */}
                <Card className="overflow-x-auto p-0">
                  <table className="w-full min-w-[900px] text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        <th className="px-4 py-3">Agent</th>
                        <th className="px-4 py-3 text-right">Total Tickets</th>
                        <th className="px-4 py-3 text-right">Reopened</th>
                        <th className="px-4 py-3 text-right">Avg Resolution (hrs)</th>
                        <th className="px-4 py-3 text-right">SLA Violations</th>
                        <th className="px-4 py-3 text-right">Avg CSAT</th>
                        <th className="px-4 py-3 text-right">DSAT</th>
                        <th className="px-4 py-3 text-right">Feedback Responses</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <SpecialistRow key={row.agent_id ?? row.agent_name} row={row} />
                      ))}
                      {data && (
                        <tr className="border-t-2 border-border bg-muted/60 font-semibold text-foreground">
                          <td className="px-4 py-3">Team totals</td>
                          <td className="px-4 py-3 text-right">{data.totals.total_tickets}</td>
                          <td className="px-4 py-3 text-right">{data.totals.reopened}</td>
                          <td className="px-4 py-3 text-right">
                            {numOrDash(data.totals.avg_resolution_hours, 1)}
                          </td>
                          <td className="px-4 py-3 text-right">{data.totals.sla_violations}</td>
                          <td className="px-4 py-3 text-right">
                            {numOrDash(data.totals.csat_avg, 1)}
                          </td>
                          <td className="px-4 py-3 text-right">{data.totals.dsat}</td>
                          <td className="px-4 py-3 text-right">{data.totals.feedback_responses}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </Card>
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}

function SpecialistRow({ row }: { row: SpecialistReportRow }) {
  return (
    <tr className="border-b border-border last:border-b-0 hover:bg-muted/40">
      <td className="px-4 py-3">
        <p className="font-medium text-foreground">{row.agent_name}</p>
        {row.agent_email && <p className="text-xs text-muted-foreground">{row.agent_email}</p>}
      </td>
      <td className="px-4 py-3 text-right">{row.total_tickets}</td>
      <td className="px-4 py-3 text-right">{row.reopened}</td>
      <td className="px-4 py-3 text-right">{numOrDash(row.avg_resolution_hours, 1)}</td>
      <td className="px-4 py-3 text-right">{row.sla_violations}</td>
      <td className="px-4 py-3 text-right">{numOrDash(row.csat_avg, 1)}</td>
      <td className="px-4 py-3 text-right">{row.dsat}</td>
      <td className="px-4 py-3 text-right">{row.feedback_responses}</td>
    </tr>
  );
}
