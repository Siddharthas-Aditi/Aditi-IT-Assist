/** Authentication store — manages login state and tokens. */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AuthUser, LoginRequest, LoginResponse, UserRole } from '@/types/auth';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

interface AuthStore {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
  setUser: (user: AuthUser) => void;
  checkAuth: () => Promise<void>;

  // Role helpers
  hasRole: (role: UserRole) => boolean;
  hasAnyRole: (...roles: UserRole[]) => boolean;
  isITStaff: () => boolean;
  isAdmin: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (credentials: LoginRequest) => {
        set({ isLoading: true });
        try {
          const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(credentials),
          });

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
          }

          const data: LoginResponse = await response.json();
          set({
            user: data.user,
            token: data.access_token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: () => {
        set({ user: null, token: null, isAuthenticated: false });
      },

      setUser: (user: AuthUser) => {
        set({ user, isAuthenticated: true });
      },

      checkAuth: async () => {
        const { token } = get();
        if (!token) return;

        try {
          const response = await fetch(`${API_BASE}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (response.ok) {
            const user = await response.json();
            set({ user, isAuthenticated: true });
          } else {
            set({ user: null, token: null, isAuthenticated: false });
          }
        } catch {
          set({ user: null, token: null, isAuthenticated: false });
        }
      },

      hasRole: (role: UserRole) => {
        const { user } = get();
        return user?.roles?.includes(role) ?? false;
      },

      hasAnyRole: (...roles: UserRole[]) => {
        const { user } = get();
        return roles.some((r) => user?.roles?.includes(r));
      },

      isITStaff: () => {
        return get().hasAnyRole('it_agent', 'it_lead', 'it_admin');
      },

      isAdmin: () => {
        return get().hasAnyRole('it_lead', 'it_admin');
      },
    }),
    {
      name: 'aditi-auth',
      partialize: (state) => ({ token: state.token, user: state.user }),
    }
  )
);
