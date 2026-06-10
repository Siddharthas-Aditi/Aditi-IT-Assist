/** Ticket detail page — employee view with timeline. */

import { useParams } from 'react-router-dom';

export function TicketDetailPage() {
  const { id } = useParams();

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold text-gray-900 mb-4">Ticket Details</h1>
      <p className="text-sm text-gray-500">Ticket ID: {id}</p>
      {/* TODO: Fetch and display ticket details, timeline, comments */}
      <div className="mt-6 bg-white rounded-lg border p-6">
        <p className="text-gray-500">Ticket detail view with timeline and updates coming soon.</p>
      </div>
    </div>
  );
}
