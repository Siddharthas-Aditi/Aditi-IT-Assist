/** Change board — drag between statuses, gated by the workflow rules. */

import { useNavigate } from "react-router-dom";

import { Board } from "../components/Board";
import { PageHeader } from "../components/chrome";
import { useToast } from "../components/toast-context";
import { ChangeTypeBadge, LevelIndicator } from "../components/ui";
import { personName } from "../data/reference";
import { logChangeActivity } from "../data/store";
import { useChanges } from "../api";
import {
  CHANGE_STATUS_LABELS,
  CHANGE_TRANSITIONS,
  type ChangeRecord,
  type ChangeStatus,
} from "../api-types";

const CHANGE_BOARD_STATUSES: ChangeStatus[] = [
  "draft",
  "planning",
  "pending_approval",
  "scheduled",
  "in_progress",
  "implemented",
];

function canDropChange(
  c: ChangeRecord,
  to: ChangeStatus,
): { ok: boolean; reason?: string } {
  if (c.status === to) return { ok: true };
  const allowed = CHANGE_TRANSITIONS[c.status] ?? [];
  if (!allowed.includes(to)) {
    return {
      ok: false,
      reason: `A change cannot move from ${CHANGE_STATUS_LABELS[c.status]} to ${CHANGE_STATUS_LABELS[to]}.`,
    };
  }
  return { ok: true };
}

export function ChangeBoardPage() {
  const changesQuery = useChanges();
  const changes = changesQuery.data?.items ?? [];
  const navigate = useNavigate();
  const toast = useToast();

  const onBoard = changes.filter((c) =>
    (CHANGE_BOARD_STATUSES as string[]).includes(c.status),
  );

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Change Board"
        crumbs={[
          { label: "Changes", to: "/itsm/changes" },
          { label: "Change Board" },
        ]}
        description="Drag a change to move it. Moves that break the workflow are rejected."
      />

      <Board<ChangeRecord, ChangeStatus>
        columns={CHANGE_BOARD_STATUSES}
        items={onBoard}
        columnOf={(c) => c.status}
        itemKey={(c) => c.id}
        canDrop={(c, col) => canDropChange(c, col)}
        onDrop={(c, col) => {
          void logChangeActivity(
            c.id,
            "Sagar J",
            `Moved to ${col} on the board`,
            { status: col },
          );
          toast.success(
            `${c.change_number} moved to ${CHANGE_STATUS_LABELS[col] ?? col}.`,
          );
        }}
        onRejected={(reason) => toast.error(reason)}
        renderCard={(c) => (
          <button
            type="button"
            onClick={() => navigate(`/itsm/changes/${c.id}`)}
            className="block w-full text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11.5px] font-semibold text-sky-700">
                {c.change_number}
              </span>
              <ChangeTypeBadge type={c.change_type} />
            </div>
            <p className="mt-1 line-clamp-2 text-[12.5px] text-slate-900">
              {c.title}
            </p>
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <LevelIndicator level={c.priority} />
              <span className="truncate text-[11px] text-slate-500">
                {personName(c.assigned_to_id)}
              </span>
            </div>
          </button>
        )}
      />
    </div>
  );
}
