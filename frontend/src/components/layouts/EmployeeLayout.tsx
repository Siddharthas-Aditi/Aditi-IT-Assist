/** Employee workspace layout with sidebar navigation. */

import { Outlet, NavLink } from 'react-router-dom';
import { MessageSquare, Ticket, User, LogOut } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';

export function EmployeeLayout() {
  const { user, logout, isITStaff } = useAuthStore();

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-lg font-bold text-indigo-700">Aditi IT Assist</h1>
          <p className="text-xs text-gray-500 mt-1">Employee Support</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          <NavLink
            to="/support/chat"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <MessageSquare size={18} />
            Support Chat
          </NavLink>
          <NavLink
            to="/support/tickets"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <Ticket size={18} />
            My Tickets
          </NavLink>
          <NavLink
            to="/support/profile"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            <User size={18} />
            Profile
          </NavLink>
        </nav>

        {/* Switch to operations if IT staff */}
        {isITStaff() && (
          <div className="p-3 border-t">
            <NavLink
              to="/operations"
              className="flex items-center gap-2 px-3 py-2 text-xs text-indigo-600 hover:bg-indigo-50 rounded"
            >
              Switch to Operations →
            </NavLink>
          </div>
        )}

        {/* User footer */}
        <div className="p-3 border-t">
          <div className="flex items-center gap-2 px-2">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 text-xs font-medium">
              {user?.full_name?.charAt(0) || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">{user?.full_name}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email}</p>
            </div>
            <button onClick={logout} className="text-gray-400 hover:text-red-500" title="Logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
