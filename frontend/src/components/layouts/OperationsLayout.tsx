/** IT Operations layout for agents, leads, admins. */

import { Outlet, NavLink } from 'react-router-dom';
import { Inbox, ClipboardList, Monitor, LayoutDashboard, LogOut } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';

export function OperationsLayout() {
  const { user, logout, isAdmin } = useAuthStore();

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <h1 className="text-lg font-bold text-emerald-400">IT Operations</h1>
          <p className="text-xs text-slate-400 mt-1">Aditi IT Assist</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          <NavLink
            to="/operations/queue"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-slate-700 text-emerald-400 font-medium' : 'text-slate-300 hover:bg-slate-800'
              }`
            }
          >
            <Inbox size={18} />
            Live Queue
          </NavLink>
          <NavLink
            to="/operations/assigned"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-slate-700 text-emerald-400 font-medium' : 'text-slate-300 hover:bg-slate-800'
              }`
            }
          >
            <ClipboardList size={18} />
            My Assigned
          </NavLink>
          <NavLink
            to="/operations/remote-assist"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-slate-700 text-emerald-400 font-medium' : 'text-slate-300 hover:bg-slate-800'
              }`
            }
          >
            <Monitor size={18} />
            Remote Assist
          </NavLink>
        </nav>

        {/* Navigation links */}
        <div className="p-3 border-t border-slate-700 space-y-1">
          {isAdmin() && (
            <NavLink
              to="/dashboard"
              className="flex items-center gap-2 px-3 py-2 text-xs text-emerald-400 hover:bg-slate-800 rounded"
            >
              <LayoutDashboard size={14} />
              Admin Dashboard
            </NavLink>
          )}
          <NavLink
            to="/support"
            className="flex items-center gap-2 px-3 py-2 text-xs text-slate-400 hover:bg-slate-800 rounded"
          >
            ← Employee View
          </NavLink>
        </div>

        {/* User footer */}
        <div className="p-3 border-t border-slate-700">
          <div className="flex items-center gap-2 px-2">
            <div className="w-8 h-8 rounded-full bg-emerald-900 flex items-center justify-center text-emerald-400 text-xs font-medium">
              {user?.full_name?.charAt(0) || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.full_name}</p>
              <p className="text-xs text-slate-400 truncate">{user?.role}</p>
            </div>
            <button onClick={() => logout()} className="text-slate-400 hover:text-red-400" title="Logout">
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
