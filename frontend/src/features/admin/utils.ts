/** Pure helpers for Admin Console presentation (no React components here). */

export const ROLE_LABELS: Record<string, string> = {
  employee: 'Employee',
  it_agent: 'IT Agent',
  it_lead: 'IT Lead',
  it_admin: 'IT Admin',
  security_auditor: 'Security Auditor',
};

export const ROLE_VARIANT: Record<
  string,
  'default' | 'primary' | 'warning' | 'success' | 'outline'
> = {
  it_admin: 'primary',
  it_lead: 'primary',
  it_agent: 'success',
  security_auditor: 'warning',
  employee: 'outline',
};

export const SEVERITY_VARIANT: Record<string, 'default' | 'warning' | 'destructive' | 'outline'> = {
  info: 'outline',
  warning: 'warning',
  error: 'destructive',
  critical: 'destructive',
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

/** Compact, locale-aware date/time. Returns '—' for null/invalid. */
export function fmtDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}
