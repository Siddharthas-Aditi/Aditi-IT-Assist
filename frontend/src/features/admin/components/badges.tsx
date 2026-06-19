/** Shared visual badges for the Admin Console (role, severity, status). */

import { Badge } from '@/components/ui';
import { ROLE_VARIANT, SEVERITY_VARIANT, roleLabel } from '../utils';

export function RoleBadge({ role }: { role: string }) {
  return <Badge variant={ROLE_VARIANT[role] ?? 'default'}>{roleLabel(role)}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge variant={SEVERITY_VARIANT[severity] ?? 'default'} className="capitalize">
      {severity}
    </Badge>
  );
}

export function StatusBadge({ active }: { active: boolean }) {
  return (
    <Badge variant={active ? 'success' : 'destructive'}>{active ? 'Active' : 'Suspended'}</Badge>
  );
}
