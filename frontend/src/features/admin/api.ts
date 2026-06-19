/** React Query hooks + API calls for the Admin Console (users, audit, stats). */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/lib/api';
import type {
  AgentWorkload,
  AuditEventDetail,
  AuditFacets,
  AuditFilters,
  AuditListResponse,
  DashboardMetrics,
  RoleSummary,
  SystemStats,
  UserDetail,
  UserFilters,
  UserListResponse,
  UserUpdatePayload,
} from './types';

const ADMIN = '/admin';

export const adminKeys = {
  all: ['admin'] as const,
  stats: ['admin', 'stats'] as const,
  dashboard: (days: number) => ['admin', 'dashboard', days] as const,
  workload: ['admin', 'workload'] as const,
  users: (filters: UserFilters) => ['admin', 'users', filters] as const,
  user: (id: string) => ['admin', 'user', id] as const,
  roles: ['admin', 'roles'] as const,
  audit: (filters: AuditFilters) => ['admin', 'audit', filters] as const,
  auditEvent: (id: string) => ['admin', 'audit-event', id] as const,
  auditFacets: ['admin', 'audit-facets'] as const,
};

// ── Stats / analytics ─────────────────────────────────────────────────

export function useSystemStats() {
  return useQuery({
    queryKey: adminKeys.stats,
    queryFn: () => apiRequest<SystemStats>(`${ADMIN}/stats`),
  });
}

export function useDashboardMetrics(rangeDays: number) {
  return useQuery({
    queryKey: adminKeys.dashboard(rangeDays),
    queryFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - rangeDays * 24 * 60 * 60 * 1000);
      return apiRequest<DashboardMetrics>('/analytics/dashboard', {
        query: { start_date: start.toISOString(), end_date: end.toISOString() },
      });
    },
  });
}

export function useAgentWorkload() {
  return useQuery({
    queryKey: adminKeys.workload,
    queryFn: () => apiRequest<AgentWorkload[]>('/analytics/workload'),
  });
}

// ── Users ────────────────────────────────────────────────────────────

export function useUsers(filters: UserFilters) {
  return useQuery({
    queryKey: adminKeys.users(filters),
    queryFn: () =>
      apiRequest<UserListResponse>(`${ADMIN}/users`, {
        query: {
          search: filters.search || undefined,
          role: filters.role || undefined,
          status: filters.status || undefined,
          limit: filters.limit ?? 25,
          offset: filters.offset ?? 0,
        },
      }),
  });
}

export function useUser(id: string | undefined) {
  return useQuery({
    queryKey: adminKeys.user(id ?? ''),
    queryFn: () => apiRequest<UserDetail>(`${ADMIN}/users/${id}`),
    enabled: Boolean(id),
  });
}

export function useRoles() {
  return useQuery({
    queryKey: adminKeys.roles,
    queryFn: () => apiRequest<RoleSummary[]>(`${ADMIN}/roles`),
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateUser(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserUpdatePayload) =>
      apiRequest<UserDetail>(`${ADMIN}/users/${id}`, { method: 'PATCH', body: payload }),
    onSuccess: (data) => {
      qc.setQueryData(adminKeys.user(id), data);
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}

export function useAssignRole(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (role: string) =>
      apiRequest<UserDetail>(`${ADMIN}/users/${id}/roles`, { method: 'POST', body: { role } }),
    onSuccess: (data) => {
      qc.setQueryData(adminKeys.user(id), data);
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}

export function useRevokeRole(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (role: string) =>
      apiRequest<UserDetail>(`${ADMIN}/users/${id}/roles/${encodeURIComponent(role)}`, {
        method: 'DELETE',
      }),
    onSuccess: (data) => {
      qc.setQueryData(adminKeys.user(id), data);
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}

// ── Audit log ─────────────────────────────────────────────────────────

export function useAuditEvents(filters: AuditFilters) {
  return useQuery({
    queryKey: adminKeys.audit(filters),
    queryFn: () =>
      apiRequest<AuditListResponse>(`${ADMIN}/audit-log`, {
        query: {
          severity: filters.severity || undefined,
          action: filters.action || undefined,
          resource_type: filters.resource_type || undefined,
          actor_email: filters.actor_email || undefined,
          search: filters.search || undefined,
          date_from: filters.date_from || undefined,
          date_to: filters.date_to || undefined,
          limit: filters.limit ?? 50,
          offset: filters.offset ?? 0,
        },
      }),
  });
}

export function useAuditEvent(id: string | undefined) {
  return useQuery({
    queryKey: adminKeys.auditEvent(id ?? ''),
    queryFn: () => apiRequest<AuditEventDetail>(`${ADMIN}/audit-log/${id}`),
    enabled: Boolean(id),
  });
}

export function useAuditFacets() {
  return useQuery({
    queryKey: adminKeys.auditFacets,
    queryFn: () => apiRequest<AuditFacets>(`${ADMIN}/audit-log/facets`),
    staleTime: 5 * 60 * 1000,
  });
}
