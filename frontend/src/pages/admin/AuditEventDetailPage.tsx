/** Audit event detail — full context + before/after payload diff. */

import { useParams } from 'react-router-dom';

import { PageHeader } from '@/components/admin';
import { Card } from '@/components/ui';
import { useAuditEvent } from '@/features/admin/api';
import { SeverityBadge } from '@/features/admin/components/badges';
import { fmtDateTime } from '@/features/admin/utils';

export function AuditEventDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data, isLoading, isError } = useAuditEvent(eventId);

  const breadcrumbs = [
    { label: 'Audit Logs', to: '/audit' },
    { label: data ? `Event ${data.id.slice(0, 8)}` : 'Event' },
  ];

  if (isLoading) {
    return (
      <>
        <PageHeader title="Audit Event" breadcrumbs={breadcrumbs} breadcrumbHome="/audit" />
        <div className="p-6 text-muted-foreground">Loading event…</div>
      </>
    );
  }

  if (isError || !data) {
    return (
      <>
        <PageHeader title="Audit Event" breadcrumbs={breadcrumbs} breadcrumbHome="/audit" />
        <div className="p-6 text-destructive">Audit event not found.</div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={data.action}
        description={data.description ?? undefined}
        breadcrumbs={breadcrumbs}
        breadcrumbHome="/audit"
        actions={<SeverityBadge severity={data.severity} />}
      />

      <div className="grid gap-6 p-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Event
          </h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="Action" value={data.action} />
            <Field label="Severity" value={<SeverityBadge severity={data.severity} />} />
            <Field label="Resource type" value={data.resource_type} />
            <Field label="Resource ID" value={data.resource_id || '—'} mono />
            <Field label="When" value={fmtDateTime(data.created_at)} />
            <Field label="Event ID" value={data.id} mono />
          </dl>
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Actor &amp; context
          </h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            <Field label="Actor" value={data.actor_email || 'system'} />
            <Field label="Actor role" value={data.actor_role || '—'} />
            <Field label="IP address" value={data.ip_address || '—'} mono />
            <Field label="User agent" value={data.user_agent || '—'} />
          </dl>
        </Card>

        {(data.old_value || data.new_value) && (
          <Card className="lg:col-span-2">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Change
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <PayloadBlock title="Before" payload={data.old_value} />
              <PayloadBlock title="After" payload={data.new_value} />
            </div>
          </Card>
        )}

        {data.metadata_json && Object.keys(data.metadata_json).length > 0 && (
          <Card className="lg:col-span-2">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Metadata
            </h2>
            <pre className="overflow-auto rounded-lg bg-muted/50 p-3 text-xs text-foreground">
              {JSON.stringify(data.metadata_json, null, 2)}
            </pre>
          </Card>
        )}
      </div>
    </>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={`mt-1 text-sm text-foreground ${mono ? 'font-mono text-xs' : ''}`}>{value}</dd>
    </div>
  );
}

function PayloadBlock({
  title,
  payload,
}: {
  title: string;
  payload?: Record<string, unknown> | null;
}) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <pre className="h-full overflow-auto rounded-lg bg-muted/50 p-3 text-xs text-foreground">
        {payload ? JSON.stringify(payload, null, 2) : '—'}
      </pre>
    </div>
  );
}
