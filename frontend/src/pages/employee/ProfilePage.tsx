/** Profile page — employee can view and update their profile basics. */

import { useAuthStore } from '@/stores/auth-store';

export function ProfilePage() {
  const { user } = useAuthStore();

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">My Profile</h1>

      <div className="bg-white rounded-lg border p-6 space-y-4">
        <div className="flex items-center gap-4 pb-4 border-b">
          <div className="w-16 h-16 rounded-full bg-indigo-100 flex items-center justify-center text-2xl font-bold text-indigo-700">
            {user?.full_name?.charAt(0) || '?'}
          </div>
          <div>
            <h2 className="text-lg font-semibold">{user?.full_name}</h2>
            <p className="text-sm text-gray-500">{user?.email}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">Employee ID</label>
            <p className="text-sm text-gray-900 mt-1">{user?.employee_id || 'N/A'}</p>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">Department</label>
            <p className="text-sm text-gray-900 mt-1">{user?.department || 'N/A'}</p>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">Role</label>
            <p className="text-sm text-gray-900 mt-1 capitalize">{user?.role?.replace('_', ' ')}</p>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 uppercase">Status</label>
            <p className="text-sm text-green-600 mt-1 font-medium">Active</p>
          </div>
        </div>
      </div>
    </div>
  );
}
