/** Asset board grouped by lifecycle state, gated by the lifecycle rules. */

import { useNavigate } from 'react-router-dom';

import { Board } from '../components/Board';
import { PageHeader } from '../components/chrome';
import { useToast } from '../components/toast-context';
import { LevelIndicator } from '../components/ui';
import { personName } from '../data/reference';
import { canMoveAsset } from '../data/rules';
import { logAssetActivity, useItsmState } from '../data/store';
import { ASSET_STATES, type Asset, type AssetState } from '../data/types';

export function AssetBoardPage() {
  const { assets } = useItsmState();
  const navigate = useNavigate();
  const toast = useToast();

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Asset Board"
        crumbs={[{ label: 'Assets', to: '/itsm/assets' }, { label: 'Board' }]}
        description="Drag an asset between lifecycle states. Moves missing required fields are rejected."
      />

      <Board<Asset, AssetState>
        columns={ASSET_STATES}
        items={assets}
        columnOf={(a) => a.assetState}
        itemKey={(a) => a.id}
        canDrop={(a, col) => canMoveAsset(a, col)}
        onDrop={(a, col) => {
          logAssetActivity(a.id, 'Sagar J', `State changed to ${col} on the board`, {
            assetState: col,
          });
          toast.success(`${a.assetTag} moved to ${col}.`);
        }}
        onRejected={(reason) => toast.error(reason)}
        renderCard={(a) => (
          <button
            type="button"
            onClick={() => navigate(`/itsm/assets/${a.id}`)}
            className="block w-full text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            <p className="text-[11.5px] font-semibold text-sky-700">{a.assetTag}</p>
            <p className="mt-0.5 line-clamp-2 text-[12.5px] text-slate-900">{a.name}</p>
            <p className="mt-0.5 text-[11px] text-slate-500">{a.assetType}</p>
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <LevelIndicator level={a.impact} />
              <span className="truncate text-[11px] text-slate-500">
                {a.assignedTo ? personName(a.assignedTo) : 'Unassigned'}
              </span>
            </div>
          </button>
        )}
      />
    </div>
  );
}
