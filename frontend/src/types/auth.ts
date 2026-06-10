/**
 * Authentication types for the enterprise platform.
 *
 * Permission logic is in `@/lib/permissions.ts`.
 * This file contains auth-related data types only.
 */

export type { UserRole, PermissionCode } from "@/lib/permissions";
export { P, DEFAULT_ROUTES as ROLE_ROUTES } from "@/lib/permissions";
export {
  isITStaff,
  isAdmin,
  isLeadOrAbove,
  hasPermission,
  canAccessRoute,
  getDefaultRoute,
} from "@/lib/permissions";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: import("@/lib/permissions").UserRole;
  roles: import("@/lib/permissions").UserRole[];
  department?: string;
  employee_id?: string;
  permissions?: import("@/lib/permissions").PermissionCode[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  user: AuthUser;
}

export interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}
