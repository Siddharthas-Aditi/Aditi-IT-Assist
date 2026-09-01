/** Change templates — list, create, edit, clone, archive. */

import { useMemo, useState } from "react";
import { Archive, Copy, Pencil, Plus, RotateCcw, Search } from "lucide-react";

import { PageHeader } from "../components/chrome";
import { useToast } from "../components/toast-context";
import {
  Button,
  ChangeTypeBadge,
  EmptyState,
  Field,
  LevelIndicator,
  Panel,
  Select,
  TextArea,
  TextInput,
} from "../components/ui";
import {
  CATEGORIES,
  DEPARTMENTS,
  MAINTENANCE_WINDOWS,
} from "../data/reference";
import { cloneTemplate, createTemplate, updateTemplate } from "../data/store";
import {
  CHANGE_TYPES,
  IMPACTS,
  PRIORITIES,
  RISKS,
  type ChangeTemplate,
} from "../data/types";
import { EMPTY_PLANNING, PLANNING_FIELDS } from "./form-model";

// Templates are not yet backed by the API (deferred feature). Using empty
// local state until a templates endpoint is available.
const EMPTY_TEMPLATES: ChangeTemplate[] = [];

function blank(): Omit<ChangeTemplate, "id" | "createdAt"> {
  return {
    name: "",
    changeType: "Normal",
    defaultPriority: "Medium",
    defaultImpact: "Low",
    defaultRisk: "Low",
    defaultCategory: "",
    defaultDepartment: "",
    defaultMaintenanceWindow: "",
    requiredApprovals: [],
    planning: { ...EMPTY_PLANNING },
    archived: false,
    lastUsedAt: null,
  };
}

export function ChangeTemplatesPage() {
  const templates = EMPTY_TEMPLATES;
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<
    (Omit<ChangeTemplate, "id" | "createdAt"> & { id?: string }) | null
  >(null);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return templates
      .filter((t) => (showArchived ? true : !t.archived))
      .filter((t) => !needle || t.name.toLowerCase().includes(needle));
  }, [templates, query, showArchived]);

  function save() {
    if (!editing) return;
    if (!editing.name.trim()) {
      toast.error("Template name is required.");
      return;
    }
    if (editing.id) {
      updateTemplate(editing.id, editing);
      toast.success("Template updated.");
    } else {
      createTemplate(editing);
      toast.success("Template created.");
    }
    setEditing(null);
  }

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Change Templates"
        crumbs={[
          { label: "Changes", to: "/itsm/changes" },
          { label: "Templates" },
        ]}
        description="Reusable defaults for recurring changes."
        actions={
          <Button variant="primary" onClick={() => setEditing(blank())}>
            <Plus size={14} /> New template
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search
            size={14}
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search templates…"
            aria-label="Search templates"
            className="w-full rounded-md border border-slate-300 bg-white py-1.5 pl-8 pr-3 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
        </div>
        <label className="flex items-center gap-1.5 text-[12.5px] text-slate-500">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-slate-300 bg-slate-100 text-sky-500 focus:ring-1 focus:ring-sky-500"
          />
          Show archived
        </label>
      </div>

      {editing && (
        <Panel title={editing.id ? "Edit template" : "New template"}>
          <div className="grid gap-3.5 sm:grid-cols-2">
            <Field
              label="Template Name"
              required
              htmlFor="tpl-name"
              className="sm:col-span-2"
            >
              <TextInput
                id="tpl-name"
                value={editing.name}
                onChange={(e) =>
                  setEditing({ ...editing, name: e.target.value })
                }
              />
            </Field>
            <Field label="Change Type" htmlFor="tpl-type">
              <Select
                id="tpl-type"
                options={CHANGE_TYPES}
                value={editing.changeType}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    changeType: e.target.value as ChangeTemplate["changeType"],
                  })
                }
              />
            </Field>
            <Field label="Default Priority" htmlFor="tpl-pri">
              <Select
                id="tpl-pri"
                options={PRIORITIES}
                value={editing.defaultPriority}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    defaultPriority: e.target
                      .value as ChangeTemplate["defaultPriority"],
                  })
                }
              />
            </Field>
            <Field label="Default Impact" htmlFor="tpl-imp">
              <Select
                id="tpl-imp"
                options={IMPACTS}
                value={editing.defaultImpact}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    defaultImpact: e.target
                      .value as ChangeTemplate["defaultImpact"],
                  })
                }
              />
            </Field>
            <Field label="Default Risk" htmlFor="tpl-risk">
              <Select
                id="tpl-risk"
                options={RISKS}
                value={editing.defaultRisk}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    defaultRisk: e.target
                      .value as ChangeTemplate["defaultRisk"],
                  })
                }
              />
            </Field>
            <Field label="Default Category" htmlFor="tpl-cat">
              <Select
                id="tpl-cat"
                options={CATEGORIES}
                placeholder="None"
                value={editing.defaultCategory}
                onChange={(e) =>
                  setEditing({ ...editing, defaultCategory: e.target.value })
                }
              />
            </Field>
            <Field label="Default Department" htmlFor="tpl-dep">
              <Select
                id="tpl-dep"
                options={DEPARTMENTS}
                placeholder="None"
                value={editing.defaultDepartment}
                onChange={(e) =>
                  setEditing({ ...editing, defaultDepartment: e.target.value })
                }
              />
            </Field>
            <Field label="Default Maintenance Window" htmlFor="tpl-win">
              <Select
                id="tpl-win"
                options={MAINTENANCE_WINDOWS}
                placeholder="None"
                value={editing.defaultMaintenanceWindow}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    defaultMaintenanceWindow: e.target.value,
                  })
                }
              />
            </Field>
            <Field
              label="Required Approvals"
              hint="Comma separated, in order."
              htmlFor="tpl-apr"
              className="sm:col-span-2"
            >
              <TextInput
                id="tpl-apr"
                value={editing.requiredApprovals.join(", ")}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    requiredApprovals: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
              />
            </Field>

            {PLANNING_FIELDS.map((f) => (
              <Field key={f.key} label={f.label} htmlFor={`tpl-${f.key}`}>
                <TextArea
                  id={`tpl-${f.key}`}
                  value={editing.planning[f.key]}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      planning: {
                        ...editing.planning,
                        [f.key]: e.target.value,
                      },
                    })
                  }
                />
              </Field>
            ))}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={save}>
              Save template
            </Button>
          </div>
        </Panel>
      )}

      {visible.length === 0 ? (
        <Panel>
          <EmptyState
            title="No templates found"
            description="Create a template to standardise recurring changes."
          />
        </Panel>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {visible.map((t) => (
            <li
              key={t.id}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate text-[13.5px] font-semibold text-slate-900">
                    {t.name}
                  </h3>
                  <p className="mt-0.5 text-[11.5px] text-slate-500">
                    {t.defaultCategory || "No category"} ·{" "}
                    {t.defaultDepartment || "No department"}
                  </p>
                </div>
                <ChangeTypeBadge type={t.changeType} />
              </div>

              <div className="mt-2.5 flex flex-wrap items-center gap-3 text-[12px]">
                <LevelIndicator level={t.defaultPriority} />
                <span className="text-slate-400">|</span>
                <span className="text-slate-500">Impact</span>
                <LevelIndicator level={t.defaultImpact} />
                <span className="text-slate-400">|</span>
                <span className="text-slate-500">Risk</span>
                <LevelIndicator level={t.defaultRisk} />
              </div>

              {t.requiredApprovals.length > 0 && (
                <p className="mt-2 text-[11.5px] text-slate-500">
                  Approvals: {t.requiredApprovals.join(" → ")}
                </p>
              )}
              {t.archived && (
                <p className="mt-1 text-[11.5px] font-medium text-amber-600">
                  Archived
                </p>
              )}

              <div className="mt-3 flex flex-wrap gap-1.5">
                <Button onClick={() => setEditing({ ...t })}>
                  <Pencil size={12} /> Edit
                </Button>
                <Button
                  onClick={() => {
                    cloneTemplate(t.id);
                    toast.success("Template cloned.");
                  }}
                >
                  <Copy size={12} /> Clone
                </Button>
                <Button
                  onClick={() => {
                    updateTemplate(t.id, { archived: !t.archived });
                    toast.info(
                      t.archived ? "Template restored." : "Template archived.",
                    );
                  }}
                >
                  {t.archived ? <RotateCcw size={12} /> : <Archive size={12} />}
                  {t.archived ? "Restore" : "Archive"}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
