/** Admin tree editor for ticket category hierarchy (L1 → L2 → L3). */

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Pencil,
  Power,
  Trash2,
} from 'lucide-react';

import { ApiError, ticketCategoriesApi, type TicketCategoryNode } from '@/lib/api';

import { isLeaf } from './categoryTreeUtils';

const LEVEL_LABELS: Record<number, string> = {
  1: 'Category',
  2: 'Sub-Category',
  3: 'Item',
};

interface Props {
  tree: TicketCategoryNode[];
  onChanged: () => Promise<void>;
  onError: (message: string | null) => void;
}

function AddRow({
  label,
  onAdd,
  busy,
}: {
  label: string;
  onAdd: (name: string) => Promise<void>;
  busy: boolean;
}) {
  const [name, setName] = useState('');
  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    await onAdd(trimmed);
    setName('');
  };

  return (
    <div className="mt-2 flex items-center gap-2 pl-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={`New ${label}…`}
        disabled={busy}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void submit();
        }}
        className="min-w-0 flex-1 rounded-md border border-border bg-card px-2.5 py-1.5 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
      />
      <button
        type="button"
        disabled={busy || !name.trim()}
        onClick={() => void submit()}
        className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
      >
        <Plus size={14} /> Add
      </button>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  expanded,
  onToggle,
  onChanged,
  onError,
  busy,
  setBusy,
}: {
  node: TicketCategoryNode;
  depth: number;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => Promise<void>;
  onError: (message: string | null) => void;
  busy: boolean;
  setBusy: (v: boolean) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(node.name);
  const [showAddChild, setShowAddChild] = useState(false);
  const leaf = isLeaf(node);
  const canAddChild = node.level < 3;
  const hasChildren = Boolean(node.children?.length);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    onError(null);
    try {
      await action();
      await onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(false);
    }
  };

  const saveRename = async () => {
    const trimmed = draftName.trim();
    if (!trimmed || trimmed === node.name) {
      setEditing(false);
      setDraftName(node.name);
      return;
    }
    await run(async () => {
      await ticketCategoriesApi.update(node.id, { name: trimmed });
    });
    setEditing(false);
  };

  const toggleActive = () =>
    run(async () => {
      await ticketCategoriesApi.update(node.id, { is_active: !node.is_active });
    });

  const deleteNode = () => {
    if (!leaf) return;
    if (!window.confirm(`Delete "${node.name}"? This cannot be undone.`)) return;
    void run(async () => {
      await ticketCategoriesApi.remove(node.id);
    });
  };

  const addChild = (name: string) =>
    run(async () => {
      await ticketCategoriesApi.create({
        name,
        level: node.level + 1,
        parent_id: node.id,
      });
      setShowAddChild(false);
    });

  return (
    <div>
      <div
        className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card px-2 py-1.5"
        style={{ marginLeft: depth * 16 }}
      >
        <button
          type="button"
          onClick={onToggle}
          className="shrink-0 text-muted-foreground"
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {hasChildren || canAddChild ? (
            expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />
          ) : (
            <span className="inline-block w-4" />
          )}
        </button>

        {editing ? (
          <input
            autoFocus
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
            onBlur={() => void saveRename()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void saveRename();
              if (e.key === 'Escape') {
                setEditing(false);
                setDraftName(node.name);
              }
            }}
            disabled={busy}
            className="min-w-[120px] flex-1 rounded border border-border px-2 py-0.5 text-sm"
          />
        ) : (
          <span className={`min-w-0 flex-1 text-sm font-medium ${!node.is_active ? 'text-muted-foreground line-through' : 'text-foreground'}`}>
            {node.name}
          </span>
        )}

        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          L{node.level}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
            node.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {node.is_active ? 'Active' : 'Inactive'}
        </span>

        <div className="flex items-center gap-1">
          {!editing && (
            <button
              type="button"
              title="Rename"
              disabled={busy}
              onClick={() => setEditing(true)}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <Pencil size={14} />
            </button>
          )}
          <button
            type="button"
            title={node.is_active ? 'Deactivate' : 'Activate'}
            disabled={busy}
            onClick={() => void toggleActive()}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
          >
            <Power size={14} />
          </button>
          {canAddChild && (
            <button
              type="button"
              title={`Add ${LEVEL_LABELS[node.level + 1]}`}
              disabled={busy}
              onClick={() => {
                setShowAddChild((v) => !v);
                onToggle();
              }}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <Plus size={14} />
            </button>
          )}
          {leaf && (
            <button
              type="button"
              title="Delete"
              disabled={busy}
              onClick={() => void deleteNode()}
              className="rounded p-1 text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {showAddChild && canAddChild && (
        <div style={{ marginLeft: (depth + 1) * 16 }}>
          <AddRow
            label={LEVEL_LABELS[node.level + 1] ?? 'child'}
            onAdd={addChild}
            busy={busy}
          />
        </div>
      )}

      {expanded &&
        node.children?.map((child) => (
          <TreeNodeWrapper
            key={child.id}
            node={child}
            depth={depth + 1}
            onChanged={onChanged}
            onError={onError}
            busy={busy}
            setBusy={setBusy}
          />
        ))}
    </div>
  );
}

function TreeNodeWrapper(props: Omit<Parameters<typeof TreeNode>[0], 'expanded' | 'onToggle'>) {
  const [expanded, setExpanded] = useState(true);
  return (
    <TreeNode
      {...props}
      expanded={expanded}
      onToggle={() => setExpanded((v) => !v)}
    />
  );
}

export function CategoryTreeEditor({ tree, onChanged, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const [showAddRoot, setShowAddRoot] = useState(false);

  const addRoot = async (name: string) => {
    setBusy(true);
    onError(null);
    try {
      await ticketCategoriesApi.create({ name, level: 1 });
      setShowAddRoot(false);
      await onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Failed to add');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Manage Category → Sub-Category → Item hierarchy used when closing tickets.
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={() => setShowAddRoot((v) => !v)}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-sm font-medium hover:bg-muted disabled:opacity-50"
        >
          <Plus size={14} /> Add Category
        </button>
      </div>

      {showAddRoot && (
        <AddRow label="Category" onAdd={addRoot} busy={busy} />
      )}

      {tree.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No categories yet — add a top-level Category to get started.
        </p>
      ) : (
        tree.map((node) => (
          <TreeNodeWrapper
            key={node.id}
            node={node}
            depth={0}
            onChanged={onChanged}
            onError={onError}
            busy={busy}
            setBusy={setBusy}
          />
        ))
      )}
    </div>
  );
}
