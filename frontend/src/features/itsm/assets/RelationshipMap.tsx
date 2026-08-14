/** Radial relationship map for an asset, plus add/remove association controls. */

import { useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { Button, EmptyState, Field, Panel, Select, TextInput } from '../components/ui';
import { newId } from '../data/store';
import {
  RELATIONSHIP_TARGETS,
  type Asset,
  type AssetRelationship,
  type RelationshipTarget,
} from '../data/types';

const NODE_TONES: Record<string, string> = {
  User: '#38bdf8',
  Change: '#a78bfa',
  Vendor: '#fbbf24',
  'Purchase Order': '#34d399',
  Contract: '#f472b6',
  'Parent Asset': '#60a5fa',
  'Child Asset': '#4ade80',
  'Application / Service': '#fb923c',
};

interface RelationshipMapProps {
  asset: Asset;
  onAdd: (rel: AssetRelationship) => void;
  onRemove: (id: string) => void;
}

export function RelationshipMap({ asset, onAdd, onRemove }: RelationshipMapProps) {
  const [type, setType] = useState<RelationshipTarget>('User');
  const [label, setLabel] = useState('');
  const [error, setError] = useState('');

  const nodes = useMemo(() => {
    const count = asset.relationships.length;
    const radius = 118;
    return asset.relationships.map((rel, i) => {
      // Distribute evenly around the centre, starting at 12 o'clock.
      const angle = (i / Math.max(count, 1)) * Math.PI * 2 - Math.PI / 2;
      return {
        rel,
        x: 200 + radius * Math.cos(angle),
        y: 160 + radius * Math.sin(angle),
      };
    });
  }, [asset.relationships]);

  function add() {
    if (!label.trim()) {
      setError('Enter the name of the related record.');
      return;
    }
    onAdd({
      id: newId('rel'),
      targetType: type,
      targetId: label.trim().toLowerCase().replace(/\s+/g, '-'),
      targetLabel: label.trim(),
      owner: 'Sagar J',
      createdAt: new Date().toISOString(),
    });
    setLabel('');
    setError('');
  }

  return (
    <div className="space-y-4">
      <Panel title="Relationship map">
        {asset.relationships.length === 0 ? (
          <EmptyState
            title="No relationships yet"
            description="Associate this asset with a user, change, vendor, contract, or another asset."
          />
        ) : (
          <div className="overflow-x-auto">
            <svg
              viewBox="0 0 400 320"
              className="mx-auto h-[320px] w-full max-w-[520px]"
              role="img"
              aria-label={`Relationship map for ${asset.assetTag} with ${asset.relationships.length} associations`}
            >
              {nodes.map(({ rel, x, y }) => (
                <line
                  key={`edge-${rel.id}`}
                  x1={200}
                  y1={160}
                  x2={x}
                  y2={y}
                  stroke="#334155"
                  strokeWidth={1.5}
                />
              ))}

              {/* Centre node — the asset itself. */}
              <circle cx={200} cy={160} r={38} fill="#0c4a6e" stroke="#0ea5e9" strokeWidth={2} />
              <text
                x={200}
                y={157}
                textAnchor="middle"
                className="fill-sky-100 text-[10px] font-semibold"
              >
                {asset.assetTag.slice(0, 12)}
              </text>
              <text x={200} y={170} textAnchor="middle" className="fill-sky-300 text-[8px]">
                {asset.assetType}
              </text>

              {nodes.map(({ rel, x, y }) => (
                <g key={rel.id}>
                  <circle
                    cx={x}
                    cy={y}
                    r={28}
                    fill="#1e293b"
                    stroke={NODE_TONES[rel.targetType] ?? '#64748b'}
                    strokeWidth={1.5}
                  />
                  <text
                    x={x}
                    y={y - 2}
                    textAnchor="middle"
                    className="fill-slate-200 text-[7.5px] font-medium"
                  >
                    {rel.targetLabel.slice(0, 14)}
                  </text>
                  <text x={x} y={y + 8} textAnchor="middle" className="fill-slate-500 text-[7px]">
                    {rel.targetType.slice(0, 16)}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        )}
      </Panel>

      <Panel title="Add association">
        <div className="grid items-end gap-3 sm:grid-cols-[180px_1fr_auto]">
          <Field label="Relationship type" htmlFor="rel-type">
            <Select
              id="rel-type"
              options={RELATIONSHIP_TARGETS}
              value={type}
              onChange={(e) => setType(e.target.value as RelationshipTarget)}
            />
          </Field>
          <Field label="Related record" error={error} htmlFor="rel-label">
            <TextInput
              id="rel-label"
              value={label}
              aria-invalid={Boolean(error)}
              onChange={(e) => {
                setLabel(e.target.value);
                setError('');
              }}
              placeholder="e.g. CHG-1001, BLR4U India, Corporate Wi-Fi Service"
            />
          </Field>
          <Button variant="primary" onClick={add}>
            <Plus size={14} /> Associate
          </Button>
        </div>
      </Panel>

      <Panel title={`Associations (${asset.relationships.length})`}>
        {asset.relationships.length === 0 ? (
          <EmptyState title="Nothing associated" />
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-200">
                {['Type', 'Related record', 'Owner', 'Created', ''].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {asset.relationships.map((rel) => (
                <tr key={rel.id} className="border-b border-slate-200 last:border-0">
                  <td className="px-2 py-1.5">
                    <span className="inline-flex items-center gap-1.5 text-[12.5px] text-slate-800">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ background: NODE_TONES[rel.targetType] ?? '#64748b' }}
                        aria-hidden="true"
                      />
                      {rel.targetType}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-[12.5px] text-slate-900">{rel.targetLabel}</td>
                  <td className="px-2 py-1.5 text-[12.5px] text-slate-500">{rel.owner}</td>
                  <td className="px-2 py-1.5 text-[12.5px] text-slate-500">
                    {new Date(rel.createdAt).toLocaleDateString()}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <Button
                      variant="ghost"
                      onClick={() => onRemove(rel.id)}
                      aria-label={`Remove association with ${rel.targetLabel}`}
                    >
                      <Trash2 size={12} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
