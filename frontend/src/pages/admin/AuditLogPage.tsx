/** Audit log viewer — security auditor and admin access. */

export function AuditLogPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Audit Log</h1>
      <p className="text-sm text-gray-500 mb-6">Security and compliance event trail</p>

      <div className="bg-white rounded-lg border">
        <div className="p-4 border-b bg-gray-50 flex items-center gap-4">
          <input placeholder="Search events..." className="flex-1 px-3 py-1.5 border rounded text-sm" />
          <select className="px-3 py-1.5 border rounded text-sm">
            <option>All Severities</option>
            <option>Critical</option>
            <option>Warning</option>
            <option>Info</option>
          </select>
        </div>
        <div className="p-8 text-center text-gray-500">
          <p>Audit events will appear here.</p>
          <p className="text-xs mt-1">Actions: login, role changes, ticket mutations, remote sessions, consent grants</p>
        </div>
      </div>
    </div>
  );
}
