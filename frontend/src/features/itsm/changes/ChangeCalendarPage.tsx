/** Month calendar of scheduled changes, placed by planned start/end. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { PageHeader } from "../components/chrome";
import { Button, EmptyState, Panel, StatusBadge } from "../components/ui";
import { useItsmState } from "../api";
import { toChangeDisplay } from "../display-adapters";
import type { ChangeDisplay as Change } from "../display-adapters";
import { cn } from "../lib/cn";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function startOfMonthGrid(year: number, month: number): Date {
  const first = new Date(year, month, 1);
  // Shift so the grid always begins on a Monday.
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  start.setHours(0, 0, 0, 0);
  return start;
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** A change occupies every day from its planned start through its planned end. */
function spansDay(change: Change, day: Date): boolean {
  const start = new Date(change.plannedStart ?? "");
  const end = new Date(change.plannedEnd ?? "");
  if (Number.isNaN(start.getTime())) return false;
  const dayStart = new Date(day);
  dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(day);
  dayEnd.setHours(23, 59, 59, 999);
  return (
    start <= dayEnd && (Number.isNaN(end.getTime()) ? start : end) >= dayStart
  );
}

export function ChangeCalendarPage() {
  const { changes: rawChanges } = useItsmState();
  const changes = rawChanges.map(toChangeDisplay);
  const navigate = useNavigate();
  const today = new Date();
  const [cursor, setCursor] = useState(
    new Date(today.getFullYear(), today.getMonth(), 1),
  );

  const days = useMemo(() => {
    const start = startOfMonthGrid(cursor.getFullYear(), cursor.getMonth());
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
  }, [cursor]);

  const scheduled = useMemo(
    () =>
      changes.filter(
        (c) => c.status !== "cancelled" && c.status !== "rejected",
      ),
    [changes],
  );

  const monthLabel = cursor.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Change Calendar"
        crumbs={[
          { label: "Changes", to: "/itsm/changes" },
          { label: "Calendar" },
        ]}
        description="Changes plotted across their planned start and end."
        actions={
          <div className="flex items-center gap-1.5">
            <Button
              onClick={() =>
                setCursor(
                  new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1),
                )
              }
              aria-label="Previous month"
            >
              <ChevronLeft size={14} />
            </Button>
            <span className="min-w-[150px] text-center text-[13px] font-medium text-slate-800">
              {monthLabel}
            </span>
            <Button
              onClick={() =>
                setCursor(
                  new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1),
                )
              }
              aria-label="Next month"
            >
              <ChevronRight size={14} />
            </Button>
            <Button
              onClick={() =>
                setCursor(new Date(today.getFullYear(), today.getMonth(), 1))
              }
            >
              Today
            </Button>
          </div>
        }
      />

      {scheduled.length === 0 ? (
        <Panel>
          <EmptyState
            title="Nothing scheduled"
            description="No active changes to display."
          />
        </Panel>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <div className="grid grid-cols-7 border-b border-slate-200 bg-white">
            {WEEKDAYS.map((d) => (
              <div
                key={d}
                className="px-2 py-1.5 text-center text-[11px] font-semibold uppercase tracking-wide text-slate-500"
              >
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day) => {
              const inMonth = day.getMonth() === cursor.getMonth();
              const isToday = sameDay(day, today);
              const dayChanges = scheduled.filter((c) => spansDay(c, day));
              return (
                <div
                  key={day.toISOString()}
                  className={cn(
                    "min-h-[104px] border-b border-r border-slate-200 p-1.5 last:border-r-0",
                    inMonth ? "bg-slate-50" : "bg-slate-50",
                  )}
                >
                  <div
                    className={cn(
                      "mb-1 inline-flex h-5 w-5 items-center justify-center rounded text-[11px]",
                      isToday
                        ? "bg-sky-600 font-semibold text-slate-900"
                        : inMonth
                          ? "text-slate-500"
                          : "text-slate-400",
                    )}
                  >
                    {day.getDate()}
                  </div>
                  <ul className="space-y-1">
                    {dayChanges.slice(0, 3).map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          onClick={() => navigate(`/itsm/changes/${c.id}`)}
                          title={`${c.changeId} — ${c.subject}`}
                          className="block w-full truncate rounded bg-slate-100 px-1.5 py-0.5 text-left text-[10.5px] text-slate-800 hover:bg-slate-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
                        >
                          <span className="text-sky-700">{c.changeId}</span>{" "}
                          {c.subject}
                        </button>
                      </li>
                    ))}
                    {dayChanges.length > 3 && (
                      <li className="px-1.5 text-[10.5px] text-slate-500">
                        +{dayChanges.length - 3} more
                      </li>
                    )}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <Panel title="Upcoming changes">
        <ul className="divide-y divide-slate-200">
          {scheduled
            .filter(
              (c) => new Date(c.plannedStart ?? "").getTime() >= Date.now(),
            )
            .sort((a, b) =>
              (a.plannedStart ?? "").localeCompare(b.plannedStart ?? ""),
            )
            .slice(0, 8)
            .map((c) => (
              <li
                key={c.id}
                className="flex items-center justify-between gap-3 py-2"
              >
                <button
                  type="button"
                  onClick={() => navigate(`/itsm/changes/${c.id}`)}
                  className="min-w-0 flex-1 text-left focus:outline-none focus-visible:underline"
                >
                  <span className="text-[13px] font-medium text-sky-700">
                    {c.changeId}
                  </span>
                  <span className="ml-2 text-[13px] text-slate-800">
                    {c.title}
                  </span>
                  <p className="text-[11.5px] text-slate-500">
                    {c.plannedStart
                      ? new Date(c.plannedStart).toLocaleString()
                      : "—"}
                  </p>
                </button>
                <StatusBadge status={c.status} />
              </li>
            ))}
        </ul>
      </Panel>
    </div>
  );
}
