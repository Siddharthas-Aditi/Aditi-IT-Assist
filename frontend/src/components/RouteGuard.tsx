/** Route guard component — enforces role-based access control on routes. */

import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import type { UserRole } from '@/types/auth';

interface RouteGuardProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
  requireAuth?: boolean;
}

export function RouteGuard({
  children,
  allowedRoles,
  requireAuth = true,
}: RouteGuardProps) {
  const { isAuthenticated, user } = useAuthStore();
  const location = useLocation();

  // Require authentication
  if (requireAuth && !isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check role access
  if (allowedRoles && user) {
    const hasAccess = allowedRoles.some((role) => user.roles.includes(role));
    if (!hasAccess) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
}

/** Convenience wrappers for common role checks */
export function EmployeeRoute({ children }: { children: React.ReactNode }) {
  return <RouteGuard>{children}</RouteGuard>;
}

export function ITStaffRoute({ children }: { children: React.ReactNode }) {
  return (
    <RouteGuard allowedRoles={['it_agent', 'it_lead', 'it_admin']}>
      {children}
    </RouteGuard>
  );
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  return (
    <RouteGuard allowedRoles={['it_lead', 'it_admin']}>
      {children}
    </RouteGuard>
  );
}

export function AuditorRoute({ children }: { children: React.ReactNode }) {
  return (
    <RouteGuard allowedRoles={['security_auditor', 'it_admin']}>
      {children}
    </RouteGuard>
  );
}
