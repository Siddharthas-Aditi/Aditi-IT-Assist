/** Assigned tickets page — IT agent's personal workload. */

export function AssignedTicketsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">My Assigned Tickets</h1>
      <p className="text-sm text-gray-500 mb-6">Tickets currently assigned to you</p>

      <div className="bg-white rounded-lg border">
        <div className="p-8 text-center text-gray-500">
          <p>Your assigned tickets will appear here.</p>
        </div>
      </div>
    </div>
  );
}
