/** Change detail — overview, planning, approvals, implementation, activity. */

import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuthStore } from "@/stores/auth-store";

import { PageHeader, Tabs } from "../components/chrome";
import { useToast } from "../components/toast-context";
import {
  Button,
  ChangeTypeBadge,
  DetailRow,
  EmptyState,
  ErrorState,
  LevelIndicator,
  Panel,
  StatusBadge,
  TextArea,
} from "../components/ui";
import { personName } from "../data/reference";
import { canMoveChange } from "../data/rules";
import { createChange, deleteChangeRecord, logChangeActivity, useItsmState } from "../api";
import type { ChangeStatus } from "../api-types";
import type { ChangeDisplay as Change } from "../display-adapters";
import { toChangeDisplay } from "../display-adapters";
import { canPerformItsmAction } from "../permissions";
import { PLANNING_FIELDS } from "./form-model";

const TABS = [
  "Overview",
  "Planning",
  "Approval",
  "Implementation",
  "Associated Assets",
  "Attachments",
  "Activity",
] as const;

const ACTOR = "Sagar J";

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ChangeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuthStore();
  const { changes } = useItsmState();
  const [tab, setTab] = useState<string>("Overview");
  const [closureDraft, setClosureDraft] = useState("");
  const canUpdate = canPerformItsmAction(user, "change:update");
  const canCreate = canPerformItsmAction(user, "change:create");
  const canApprove = canPerformItsmAction(user, "change:approve");
  const canImplement = canPerformItsmAction(user, "change:implement");
  const canClose = canPerformItsmAction(user, "change:close");
  const canDelete = canPerformItsmAction(user, "change:delete");

  const changeRaw = useMemo(
    () => changes.find((c) => c.id === id || c.change_number === id),
    [changes, id],
  );
  const change = useMemo(
    () => (changeRaw ? toChangeDisplay(changeRaw) : undefined),
    [changeRaw],
  );

  if (!change) return <ErrorState message={`No change found for "${id}".`} />;

  /** Every status action funnels through the shared rule check. */
  function move(to: ChangeStatus, extra: Partial<Change> = {}, label?: string) {
    if (!change) return;
    const merged = { ...change, ...extra };
    const verdict = canMoveChange(
      merged as unknown as Parameters<typeof canMoveChange>[0],
      to as unknown as Parameters<typeof canMoveChange>[1],
    );
    if (!verdict.ok) {
      toast.error(verdict.reason ?? "That transition is not allowed.");
      return;
    }
    logChangeActivity(change.id, ACTOR, label ?? `Status changed to ${to}`, {
      ...extra,
      status: to,
    });
    toast.success(label ?? `Change moved to ${to}.`);
  }

  function decide(stageId: string, decision: "Approved" | "Rejected") {
    if (!change) return;
    const approvals = change.approvals.map((a) =>
      a.id === stageId
        ? {
            ...a,
            decision,
            decidedAt: new Date().toISOString(),
            comments:
              a.comments ||
              (decision === "Approved" ? "Approved." : "Rejected."),
          }
        : a,
    ) as typeof change.approvals;
    if (decision === "Rejected") {
      logChangeActivity(change.id, ACTOR, "Change rejected", {
        approvals,
        status: "rejected" as const,
      });
      toast.info("Change rejected.");
      return;
    }
    logChangeActivity(change.id, ACTOR, "Approval recorded", {
      approvals: approvals as unknown as typeof change.approvals,
    });
    toast.success("Approval recorded.");
  }

  function toggleTask(taskId: string) {
    if (!change) return;
    const implementationTasks = change.implementationTasks.map((t) =>
      t.id === taskId ? { ...t, done: !t.done } : t,
    );
    logChangeActivity(change.id, ACTOR, "Implementation task updated", {
      implementationTasks,
    });
  }

  function duplicate() {
    if (!change) return;
    void createChange({
      title: `${change.title} (copy)`,
      change_type: change.change_type,
      status: "draft",
      description: change.description,
      priority: change.priority,
      impact: change.impact,
      risk: change.risk,
      category: change.category,
      requested_by_id: change.requesterId,
      assigned_to_id: change.agentId,
      department: change.department,
      planned_start: change.planned_start,
      planned_end: change.planned_end,
      maintenance_window: change.maintenance_window,
      source_ticket_id: change.source_ticket_id,
      planning_data: change.planning_data,
    } as Parameters<typeof createChange>[0])
      .then((copy) => {
        toast.success(`Created ${copy.change_number} as a copy.`);
        navigate(`/itsm/changes/${copy.id}`);
      })
      .catch(() => toast.error("Failed to duplicate."));
  }

  function removeChange() {
    if (!change) return;
    if (!window.confirm(`Delete ${change.change_number}? This cannot be undone.`)) return;
    void deleteChangeRecord(change.id)
      .then(() => {
        toast.success(`${change.change_number} deleted.`);
        navigate("/itsm/changes");
      })
      .catch(() => toast.error("Failed to delete change."));
  }

  const pendingApprovals = change.approvals.filter(
    (a) => !a.decision || a.decision === "pending",
  );

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title={change.subject}
        crumbs={[
          { label: "Changes", to: "/itsm/changes" },
          { label: change.change_number },
        ]}
        description={`${change.change_number} · ${change.category || "Uncategorised"} · ${change.group || "Unassigned group"}`}
        actions={
          <>
            <StatusBadge status={change.status} />
            <ChangeTypeBadge type={change.changeType} />
            {canUpdate && <Button onClick={() => navigate(`/itsm/changes/${change.id}/edit`)}>
              Edit
            </Button>}
            {canCreate && <Button onClick={duplicate}>Duplicate</Button>}
            {canUpdate && change.status !== "pending_approval" &&
              change.status !== "implemented" && (
                <Button
                  onClick={() =>
                    move("pending_approval", {}, "Submitted for approval")
                  }
                >
                  Submit for Approval
                </Button>
              )}
            {canApprove && pendingApprovals.length > 0 && (
              <>
                <Button
                  variant="primary"
                  onClick={() => decide(pendingApprovals[0].id, "Approved")}
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  onClick={() => decide(pendingApprovals[0].id, "Rejected")}
                >
                  Reject
                </Button>
              </>
            )}
            {canUpdate && <Button onClick={() => move("scheduled")}>Schedule</Button>}
            {canImplement && <Button
              onClick={() =>
                move(
                  "in_progress",
                  { actual_start: new Date().toISOString() },
                  "Implementation started",
                )
              }
            >
              Start Implementation
            </Button>}
            {canImplement && <Button
              variant="primary"
              onClick={() =>
                move(
                  "implemented",
                  {
                    closure_notes: closureDraft || change.closureNotes,
                    actual_end: new Date().toISOString(),
                  },
                  "Change completed",
                )
              }
            >
              Complete
            </Button>}
            {canClose && change.status === "implemented" && (
              <Button variant="primary" onClick={() => move("closed", {}, "Change closed")}>
                Close Change
              </Button>
            )}
            {canUpdate && <Button variant="danger" onClick={() => move("cancelled")}>
              Cancel Change
            </Button>}
            {canDelete && <Button variant="danger" onClick={removeChange}>
              Delete Change
            </Button>}
          </>
        }
      />

      <div className="flex flex-col gap-4 lg:flex-row">
        <Tabs
          tabs={TABS}
          active={tab}
          onChange={setTab}
          orientation="vertical"
        />

        <div className="min-w-0 flex-1 space-y-4">
          {tab === "Overview" && (
            <Panel title="Overview">
              <dl className="grid gap-x-6 sm:grid-cols-2">
                <DetailRow label="Requester">
                  {personName(change.requesterId)}
                </DetailRow>
                <DetailRow label="Department">{change.department}</DetailRow>
                <DetailRow label="Change Type">
                  <ChangeTypeBadge type={change.changeType} />
                </DetailRow>
                <DetailRow label="Status">
                  <StatusBadge status={change.status} />
                </DetailRow>
                <DetailRow label="Priority">
                  <LevelIndicator level={change.priority} />
                </DetailRow>
                <DetailRow label="Impact">
                  <LevelIndicator level={change.impact} />
                </DetailRow>
                <DetailRow label="Risk">
                  <LevelIndicator level={change.risk} />
                </DetailRow>
                <DetailRow label="Group">{change.group}</DetailRow>
                <DetailRow label="Agent">
                  {personName(change.agentId)}
                </DetailRow>
                <DetailRow label="Department">{change.department}</DetailRow>
                <DetailRow label="Category">{change.category}</DetailRow>
                <DetailRow label="Maintenance Window">
                  {change.maintenanceWindow}
                </DetailRow>
                <DetailRow label="Planned Start">
                  {fmt(change.planned_start)}
                </DetailRow>
                <DetailRow label="Planned End">
                  {fmt(change.planned_end)}
                </DetailRow>
                <DetailRow label="Actual Start">
                  {fmt(change.actual_start)}
                </DetailRow>
                <DetailRow label="Actual End">
                  {fmt(change.actual_end)}
                </DetailRow>
                <DetailRow label="Created">{fmt(change.createdAt)}</DetailRow>
                <DetailRow label="Updated">{fmt(change.updatedAt)}</DetailRow>
                {change.sourceTicketId && (
                  <DetailRow label="Source Ticket">
                    <Link
                      to={`/operations/tickets/${change.sourceTicketId}`}
                      className="text-sky-700 hover:underline"
                    >
                      {change.sourceTicketNumber || "View ticket"}
                    </Link>
                  </DetailRow>
                )}
              </dl>

              {change.emergencyJustification && (
                <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3">
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-red-600">
                    Emergency justification
                  </p>
                  <p className="text-[13px] text-red-800">
                    {change.emergencyJustification}
                  </p>
                </div>
              )}

              <div className="mt-4">
                <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
                  Description
                </p>
                <div
                  className="prose-sm max-w-none text-[13px] leading-relaxed text-slate-800 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5"
                  // Description is authored in-app by IT staff via the rich-text
                  // editor; there is no untrusted external source for this field.
                  dangerouslySetInnerHTML={{ __html: change.description }}
                />
              </div>
            </Panel>
          )}

          {tab === "Planning" && (
            <Panel title="Planning">
              <dl className="space-y-3">
                {PLANNING_FIELDS.map((f) => (
                  <div key={f.key}>
                    <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                      {f.label}
                    </dt>
                    <dd className="mt-0.5 whitespace-pre-wrap text-[13px] text-slate-800">
                      {(change.planning as unknown as Record<string, string>)[
                        f.key
                      ] || "—"}
                    </dd>
                  </div>
                ))}
              </dl>
            </Panel>
          )}

          {tab === "Approval" && (
            <Panel title="Approvals">
              {change.approvals.length === 0 ? (
                <EmptyState
                  title="No approval stages"
                  description="This change has not been submitted for approval yet."
                />
              ) : (
                <ol className="space-y-3">
                  {change.approvals.map((a) => (
                    <li
                      key={a.id}
                      className="rounded-md border border-slate-200 bg-white p-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-[13px] font-medium text-slate-900">
                            Stage {a.stage} · {a.name}
                          </p>
                          <p className="text-[12px] text-slate-500">
                            Approver: {a.approverName}
                          </p>
                        </div>
                        <StatusBadge status={a.decision} />
                      </div>
                      <dl className="mt-2 grid gap-x-6 sm:grid-cols-2">
                        <DetailRow label="Decision">{a.decision}</DetailRow>
                        <DetailRow label="Decided at">
                          {fmt(a.decidedAt)}
                        </DetailRow>
                        <DetailRow label="Comments">{a.comments}</DetailRow>
                      </dl>
                      {canApprove && (!a.decision || a.decision === "pending") && (
                        <div className="mt-2 flex gap-2">
                          <Button
                            variant="primary"
                            onClick={() => decide(a.id, "Approved")}
                          >
                            Approve
                          </Button>
                          <Button
                            variant="danger"
                            onClick={() => decide(a.id, "Rejected")}
                          >
                            Reject
                          </Button>
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          )}

          {tab === "Implementation" && (
            <div className="space-y-4">
              <Panel title="Implementation tasks">
                <ul className="space-y-1.5">
                  {change.implementationTasks.map((t) => (
                    <li key={t.id}>
                      <label className="flex items-start gap-2 text-[13px] text-slate-800">
                        <input
                          type="checkbox"
                          checked={t.done}
                          onChange={() => toggleTask(t.id)}
                          className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300 bg-slate-100 text-sky-500 focus:ring-1 focus:ring-sky-500"
                        />
                        <span
                          className={
                            t.done ? "text-slate-500 line-through" : undefined
                          }
                        >
                          {t.label}
                        </span>
                      </label>
                    </li>
                  ))}
                  {change.implementationTasks.length === 0 && (
                    <li className="text-[12.5px] text-slate-500">
                      No tasks captured. Add implementation steps in Planning.
                    </li>
                  )}
                </ul>
              </Panel>

              <Panel title="Plans">
                <dl className="space-y-3">
                  {(
                    [
                      "rolloutPlan",
                      "backupPlan",
                      "implementationSteps",
                      "validationPlan",
                    ] as const
                  ).map((key) => {
                    const meta = PLANNING_FIELDS.find((f) => f.key === key);
                    return (
                      <div key={key}>
                        <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                          {meta?.label}
                        </dt>
                        <dd className="mt-0.5 whitespace-pre-wrap text-[13px] text-slate-800">
                          {(
                            change.planning as unknown as Record<string, string>
                          )[key] || "—"}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              </Panel>

              <Panel title="Completion">
                <dl className="grid gap-x-6 sm:grid-cols-2">
                  <DetailRow label="Actual Start">
                    {fmt(change.actual_start)}
                  </DetailRow>
                  <DetailRow label="Actual End">
                    {fmt(change.actual_end)}
                  </DetailRow>
                </dl>
                <div className="mt-3 space-y-1">
                  <label
                    htmlFor="closure"
                    className="block text-[12px] font-medium text-slate-700"
                  >
                    Closure notes
                    <span className="ml-0.5 text-red-600">*</span>
                  </label>
                  <TextArea
                    id="closure"
                    value={closureDraft || change.closureNotes}
                    onChange={(e) => setClosureDraft(e.target.value)}
                    placeholder="Required before a change can be completed."
                  />
                  <Button
                    onClick={() => {
                      logChangeActivity(
                        change.id,
                        ACTOR,
                        "Closure notes saved",
                        {
                          closure_notes: closureDraft || change.closureNotes,
                        },
                      );
                      toast.success("Closure notes saved.");
                    }}
                  >
                    Save closure notes
                  </Button>
                </div>
              </Panel>
            </div>
          )}

          {tab === "Associated Assets" && (
            <Panel title="Associated assets unavailable">
              <EmptyState
                title="Asset-link read API is not available"
                description="Changes accept asset IDs when created, but the current backend does not expose a change asset-links read endpoint or return link data in the Change response. This page intentionally does not claim that no assets are linked."
              />
            </Panel>
          )}

          {tab === "Attachments" && (
            <Panel title="Attachments (0)">
              <EmptyState
                title="No attachments"
                description="Nothing has been uploaded."
              />
            </Panel>
          )}

          {tab === "Activity" && (
            <Panel title="Activity timeline">
              <ol className="relative space-y-3 border-l border-slate-200 pl-4">
                {[...change.activity].reverse().map((e) => (
                  <li key={e.id} className="relative">
                    <span
                      className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-sky-500"
                      aria-hidden="true"
                    />
                    <p className="text-[13px] text-slate-800">{e.action}</p>
                    <p className="text-[11.5px] text-slate-500">
                      {e.actor} · {fmt(e.at)}
                    </p>
                    {e.detail && (
                      <p className="text-[12px] text-slate-500">{e.detail}</p>
                    )}
                  </li>
                ))}
              </ol>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
