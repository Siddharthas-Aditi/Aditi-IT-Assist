/** Admin/Lead dashboard layout. */

import { Outlet, NavLink } from 'react-router-dom';
import { BarChart3, Users, BookOpen, Shield, Settings, LogOut } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';

export function AdminLayout() {
  const { user, logout } = useAuthStore();

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-indigo-950 text-white flex flex-col">
        <div className="p-4 border-b border-indigo-800">
          <h1 className="text-lg font-bold text-indigo-300">Admin Console</h1>
          <p className="text-xs text-indigo-400 mt-1">Aditi IT Assist</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          <NavLink
            to="/dashboard"
            end
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-800 text-indigo-200 font-medium' : 'text-indigo-300 hover:bg-indigo-900'
              }`
            }
          >
            <BarChart3 size={18} />
            Analytics
          </NavLink>
          <NavLink
            to="/dashboard/team-queue"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-800 text-indigo-200 font-medium' : 'text-indigo-300 hover:bg-indigo-900'
              }`
            }
          >
            <Users size={18} />
            Team Queue
          </NavLink>
          <NavLink
            to="/dashboard/knowledge"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-800 text-indigo-200 font-medium' : 'text-indigo-300 hover:bg-indigo-900'
              }`
            }
          >
            <BookOpen size={18} />
            Knowledge Base
          </NavLink>
          <NavLink
            to="/dashboard/users"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-800 text-indigo-200 font-medium' : 'text-indigo-300 hover:bg-indigo-900'
              }`
            }
          >
            <Settings size={18} />
            User Management
          </NavLink>
          <NavLink
            to="/audit"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                isActive ? 'bg-indigo-800 text-indigo-200 font-medium' : 'text-indigo-300 hover:bg-indigo-900'
              }`
            }
          >
            <Shield size={18} />
            Audit Logs
          </NavLink>
        </nav>

        {/* Quick links */}
        <div className="p-3 border-t border-indigo-800 space-y-1">
          <NavLink
            to="/operations"
            className="flex items-center gap-2 px-3 py-2 text-xs text-indigo-400 hover:bg-indigo-900 rounded"
          >
            ← Operations View
          </NavLink>
        </div>

        {/* User footer */}
        <div className="p-3 border-t border-indigo-800">
          <div className="flex items-center gap-2 px-2">
            <div className="w-8 h-8 rounded-full bg-indigo-800 flex items-center justify-center text-indigo-300 text-xs font-medium">
              {user?.full_name?.charAt(0) || '?'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.full_name}</p>
              <p className="text-xs text-indigo-400 truncate">{user?.role}</p>
            </div>
            <button onClick={() => logout()} className="text-indigo-400 hover:text-red-400" title="Logout">
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
