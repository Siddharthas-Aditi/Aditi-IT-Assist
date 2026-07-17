/** React Query hooks + API calls for the Device Execution console. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiRequest } from '@/lib/api';
import type {
  DeviceActionOutcome,
  DeviceActionRequest,
  DeviceApprovalDecision,
  DeviceCatalog,
} from './types';

const DEVICE_EXEC = '/device-execution';

export const deviceExecKeys = {
  all: ['device-execution'] as const,
  catalog: ['device-execution', 'catalog'] as const,
};

// ── Catalog ───────────────────────────────────────────────────────────

export function useDeviceCatalog() {
  return useQuery({
    queryKey: deviceExecKeys.catalog,
    queryFn: () => apiRequest<DeviceCatalog>(`${DEVICE_EXEC}/catalog`),
  });
}

// ── Request an action ─────────────────────────────────────────────────

export function useRequestDeviceAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DeviceActionRequest) =>
      apiRequest<DeviceActionOutcome>(`${DEVICE_EXEC}/actions`, {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      // A queued action shows up in the shared approvals queue.
      qc.invalidateQueries({ queryKey: ['agent-ops', 'approvals'] });
    },
  });
}

// ── Approve / reject a parked device action ───────────────────────────

export function useApproveDeviceAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DeviceApprovalDecision }) =>
      apiRequest<DeviceActionOutcome>(`${DEVICE_EXEC}/approvals/${id}/approve`, {
        method: 'POST',
        body,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-ops', 'approvals'] });
    },
  });
}

export function useRejectDeviceAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<DeviceActionOutcome>(`${DEVICE_EXEC}/approvals/${id}/reject`, {
        method: 'POST',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-ops', 'approvals'] });
    },
  });
}
