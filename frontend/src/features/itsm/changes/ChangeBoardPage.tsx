/** Change board — drag between statuses, gated by the workflow rules. */

import { useNavigate } from 'react-router-dom';

import { Board } from '../components/Board';
import { PageHeader } from '../components/chrome';
import { useToast } from '../components/toast-context';
import { ChangeTypeBadge, LevelIndicator } from '../components/ui';
import { personName } from '../data/reference';
import { canMoveChange } from '../data/rules';
import { logChangeActivity, useItsmState } from '../data/store';
import { CHANGE_BOARD_STATUSES, type Change, type ChangeStatus } from '../data/types';

export function ChangeBoardPage() {
  const { changes } = useItsmState();
  const navigate = useNavigate();
  const toast = useToast();

  const onBoard = changes.filter((c) =>
    (CHANGE_BOARD_STATUSES as string[]).includes(c.status),
  );

  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Change Board"
        crumbs={[{ label: 'Changes', to: '/itsm/changes' }, { label: 'Change Board' }]}
        description="Drag a change to move it. Moves that break the workflow are rejected."
      />

      <Board<Change, ChangeStatus>
        columns={CHANGE_BOARD_STATUSES}
        items={onBoard}
        columnOf={(c) => c.status}
        itemKey={(c) => c.id}
        canDrop={(c, col) => canMoveChange(c, col)}
        onDrop={(c, col) => {
          logChangeActivity(c.id, 'Sagar J', `Moved to ${col} on the board`, { status: col });
          toast.success(`${c.changeId} moved to ${col}.`);
        }}
        onRejected={(reason) => toast.error(reason)}
        renderCard={(c) => (
          <button
            type="button"
            onClick={() => navigate(`/itsm/changes/${c.id}`)}
            className="block w-full text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11.5px] font-semibold text-sky-700">{c.changeId}</span>
              <ChangeTypeBadge type={c.changeType} />
            </div>
            <p className="mt-1 line-clamp-2 text-[12.5px] text-slate-900">{c.subject}</p>
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <LevelIndicator level={c.priority} />
              <span className="truncate text-[11px] text-slate-500">
                {personName(c.agentId)}
              </span>
            </div>
          </button>
        )}
      />
    </div>
  );
}
