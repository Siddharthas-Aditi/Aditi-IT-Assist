/** Ticket workspace page — IT agent detailed ticket view with AI copilot. */

import { useParams } from 'react-router-dom';

export function TicketWorkspacePage() {
  const { id } = useParams();

  return (
    <div className="flex h-full">
      {/* Main ticket area */}
      <div className="flex-1 p-6 overflow-auto">
        <h1 className="text-xl font-bold text-gray-900 mb-4">Ticket Workspace</h1>
        <p className="text-sm text-gray-500 mb-6">Ticket ID: {id}</p>

        <div className="bg-white rounded-lg border p-6">
          <p className="text-gray-500">Full ticket workspace with employee context, timeline, and actions.</p>
        </div>
      </div>

      {/* AI Copilot side panel */}
      <aside className="w-80 border-l bg-white p-4 overflow-auto">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">AI Copilot</h2>
        <div className="space-y-3">
          <div className="p-3 bg-indigo-50 rounded-lg">
            <p className="text-xs font-medium text-indigo-700">Suggested Resolution</p>
            <p className="text-xs text-gray-600 mt-1">AI suggestions will appear here based on ticket context.</p>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="text-xs font-medium text-gray-700">Related Articles</p>
            <p className="text-xs text-gray-500 mt-1">Knowledge base matches will be shown here.</p>
          </div>
        </div>
      </aside>
    </div>
  );
}
