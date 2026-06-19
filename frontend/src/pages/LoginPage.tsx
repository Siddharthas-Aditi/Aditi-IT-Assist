import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { ROLE_ROUTES } from '@/types/auth';

/** Human-readable banner shown when we land on /login with ?reason=…
 *  These come from `auth-store.logout({ reason })` which is centralized,
 *  so the wording is in one place. */
const REASON_BANNERS: Record<string, string> = {
  expired: 'Your session expired. Please sign in again.',
  session_expired: 'Your session expired. Please sign in again.',
  refresh_failed: 'We could not extend your session. Please sign in again.',
  auth_required: 'Please sign in to continue.',
};

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuthStore();
  const [searchParams] = useSearchParams();
  const reason = searchParams.get('reason');
  const next = searchParams.get('next');
  const reasonMessage = reason ? REASON_BANNERS[reason] : null;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({ email, password });
      const { user } = useAuthStore.getState();
      // Respect `next=` if it's a same-origin relative path — never a full
      // URL (open-redirect guard).
      const safeNext =
        next && next.startsWith('/') && !next.startsWith('//') ? next : null;
      const defaultRoute = user ? ROLE_ROUTES[user.role] || '/support' : '/support';
      navigate(safeNext ?? defaultRoute, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 to-slate-100">
      <div className="w-full max-w-md rounded-xl border bg-white p-8 shadow-lg">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600">
            <span className="text-lg font-bold text-white">A</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Aditi IT Assist</h1>
          <p className="mt-2 text-sm text-gray-500">
            Enterprise IT Support Platform
          </p>
        </div>

        {reasonMessage && !error && (
          <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
            {reasonMessage}
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@aditi.com"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              required
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        {/* Dev credentials hint */}
        <div className="mt-6 p-3 bg-gray-50 rounded-lg">
          <p className="text-xs font-medium text-gray-600 mb-2">Dev Accounts:</p>
          <div className="text-xs text-gray-500 space-y-0.5">
            <p>Employee: alice.johnson@aditi.com / employee123</p>
            <p>IT Agent: charlie.agent@aditi.com / agent123</p>
            <p>IT Lead: edward.lead@aditi.com / lead123</p>
            <p>Admin: admin@aditi.com / admin123</p>
          </div>
        </div>

        <p className="mt-4 text-center text-xs text-gray-400">
          Enterprise SSO: SAML integration available for production
        </p>
      </div>
    </div>
  );
}
