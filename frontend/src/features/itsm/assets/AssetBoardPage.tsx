/** Asset board grouped by lifecycle state, gated by the lifecycle rules. */

import { useNavigate } from "react-router-dom";

import { Board } from "../components/Board";
import { PageHeader } from "../components/chrome";
import { useToast } from "../components/toast-context";
import { LevelIndicator } from "../components/ui";
import { personName } from "../data/reference";
import { logAssetActivity } from "../api";
import { useAssets } from "../api";
import {
  ASSET_STATUS_LABELS,
  ASSET_TERMINAL,
  type AssetRecord,
  type AssetStatus,
} from "../api-types";

const ASSET_BOARD_STATUSES: AssetStatus[] = [
  "in_stock",
  "assigned",
  "in_use",
  "under_repair",
  "reserved",
  "retired",
];

function canDropAsset(
  a: AssetRecord,
  to: AssetStatus,
): { ok: boolean; reason?: string } {
  if (a.status === to) return { ok: true };
  if (ASSET_TERMINAL.has(a.status) && (to === "assigned" || to === "in_use")) {
    return {
      ok: false,
      reason: `A ${ASSET_STATUS_LABELS[a.status]} asset cannot be re-assigned. Mark it in-stock first.`,
    };
  }
  return { ok: true };
}

export function AssetBoardPage() {
  const assetsQuery = useAssets();
  const assets = assetsQuery.data?.items ?? [];
  const navigate = useNavigate();
  const toast = useToast();

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Asset Board"
        crumbs={[{ label: "Assets", to: "/itsm/assets" }, { label: "Board" }]}
        description="Drag an asset between lifecycle states. Moves missing required fields are rejected."
      />

      <Board<AssetRecord, AssetStatus>
        columns={ASSET_BOARD_STATUSES}
        items={assets}
        columnOf={(a) => a.status}
        itemKey={(a) => a.id}
        canDrop={(a, col) => canDropAsset(a, col)}
        onDrop={(a, col) => {
          void logAssetActivity(
            a.id,
            "Sagar J",
            `Status changed to ${col} on the board`,
            {
              status: col,
            },
          );
          toast.success(
            `${a.asset_tag} moved to ${ASSET_STATUS_LABELS[col] ?? col}.`,
          );
        }}
        onRejected={(reason) => toast.error(reason)}
        renderCard={(a) => (
          <button
            type="button"
            onClick={() => navigate(`/itsm/assets/${a.id}`)}
            className="block w-full text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            <p className="text-[11.5px] font-semibold text-sky-700">
              {a.asset_tag}
            </p>
            <p className="mt-0.5 line-clamp-2 text-[12.5px] text-slate-900">
              {a.name}
            </p>
            <p className="mt-0.5 text-[11px] text-slate-500">{a.asset_type}</p>
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <LevelIndicator level={a.impact} />
              <span className="truncate text-[11px] text-slate-500">
                {a.assigned_to_id ? personName(a.assigned_to_id) : "Unassigned"}
              </span>
            </div>
          </button>
        )}
      />
    </div>
  );
}
