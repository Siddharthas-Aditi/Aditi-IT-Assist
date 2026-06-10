/** Live queue page — IT agent view of incoming support requests. */

import { useState } from 'react';

export function LiveQueuePage() {
  const [filter, setFilter] = useState('all');

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Live Support Queue</h1>
          <p className="text-sm text-gray-500 mt-1">Incoming tickets and live support requests</p>
        </div>
        <div className="flex gap-2">
          {['all', 'new', 'escalated', 'live'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs rounded-full font-medium ${
                filter === f ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Queue stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-red-600">3</p>
          <p className="text-xs text-gray-500 mt-1">Unassigned</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-yellow-600">5</p>
          <p className="text-xs text-gray-500 mt-1">In Progress</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-orange-600">2</p>
          <p className="text-xs text-gray-500 mt-1">SLA At Risk</p>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <p className="text-2xl font-bold text-green-600">12</p>
          <p className="text-xs text-gray-500 mt-1">Resolved Today</p>
        </div>
      </div>

      {/* Queue list placeholder */}
      <div className="bg-white rounded-lg border">
        <div className="p-4 border-b bg-gray-50">
          <h2 className="text-sm font-medium text-gray-700">Queue Items</h2>
        </div>
        <div className="p-8 text-center text-gray-500">
          <p>Queue items will appear here.</p>
          <p className="text-sm mt-1">Connect to backend to see live data.</p>
        </div>
      </div>
    </div>
  );
}
