import { useEffect, useState } from 'react';
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
  logged_out_other_tab: 'You were signed out from another tab.',
};

/** Local-dev roster seeded on backend startup — keep in sync with
 *  `backend/scripts/seed_enterprise.py` SAMPLE_USERS. */
const DEV_ACCOUNTS = [
  {
    role: 'Admin',
    email: 'hareesh@aditiconsulting.com',
    password: 'Hareesh@2026',
  },
  {
    role: 'IT Lead',
    email: 'sagar@aditiconsulting.com',
    password: 'Sagar@2026',
  },
  {
    role: 'IT Lead',
    email: 'madhukar@aditiconsulting.com',
    password: 'Madhukar@2026',
  },
  {
    role: 'Employee',
    email: 'siddhartha@aditiconsulting.com',
    password: 'Siddhartha@2026',
  },
  {
    role: 'Employee',
    email: 'naresh@aditiconsulting.com',
    password: 'Naresh@2026',
  },
] as const;

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login, isAuthenticated, user } = useAuthStore();
  const [searchParams] = useSearchParams();
  const reason = searchParams.get('reason');
  const next = searchParams.get('next');
  const reasonMessage = reason ? REASON_BANNERS[reason] : null;

  // If the user is already authenticated (e.g. opened a new tab while logged
  // in on another tab), skip the login form and go straight to the app.
  useEffect(() => {
    if (isAuthenticated && user && !reason) {
      const safeNext =
        next && next.startsWith('/') && !next.startsWith('//') ? next : null;
      const defaultRoute = ROLE_ROUTES[user.role] || '/support';
      navigate(safeNext ?? defaultRoute, { replace: true });
    }
  }, [isAuthenticated, user, reason, next, navigate]);

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
              placeholder="you@aditiconsulting.com"
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

        {/* Dev credentials — click a row to fill the form */}
        <div className="mt-6 rounded-lg bg-gray-50 p-3">
          <p className="mb-2 text-xs font-medium text-gray-600">
            Dev Accounts (click to fill):
          </p>
          <div className="space-y-1">
            {DEV_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                onClick={() => {
                  setEmail(account.email);
                  setPassword(account.password);
                  setError('');
                }}
                className="block w-full rounded-md px-2 py-1.5 text-left text-xs text-gray-600 transition-colors hover:bg-white hover:text-indigo-700"
              >
                <span className="font-medium text-gray-700">{account.role}:</span>{' '}
                {account.email} / {account.password}
              </button>
            ))}
          </div>
        </div>

        <p className="mt-4 text-center text-xs text-gray-400">
          Enterprise SSO: SAML integration available for production
        </p>
      </div>
    </div>
  );
}
