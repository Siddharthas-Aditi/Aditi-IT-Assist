import { Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth-store";
import {
  RouteGuard,
  ITStaffRoute,
  AdminRoute,
  AuditorRoute,
  ITAdminRoute,
} from "@/components/RouteGuard";
import { ROLE_ROUTES } from "@/types/auth";

// Layouts
import { EmployeeLayout } from "@/components/layouts/EmployeeLayout";
import { OperationsLayout } from "@/components/layouts/OperationsLayout";
import { AdminLayout } from "@/components/layouts/AdminLayout";

// Pages
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { UnauthorizedPage } from "@/pages/UnauthorizedPage";

// Employee pages
import { SupportChatPage } from "@/pages/employee/SupportChatPage";
import { MyTicketsPage } from "@/pages/employee/MyTicketsPage";
import { TicketDetailPage } from "@/pages/employee/TicketDetailPage";
import { ProfilePage } from "@/pages/employee/ProfilePage";

// IT Operations pages
import { LiveQueuePage } from "@/pages/operations/LiveQueuePage";
import { AssignedTicketsPage } from "@/pages/operations/AssignedTicketsPage";
import { LiveChatPage } from "@/pages/operations/LiveChatPage";
import { TicketWorkspacePage } from "@/pages/operations/TicketWorkspacePage";
import { RemoteAssistPage } from "@/pages/operations/RemoteAssistPage";
import { ApprovalsPage } from "@/pages/operations/ApprovalsPage";
import { DeviceActionsPage } from "@/pages/operations/DeviceActionsPage";

// Admin/Lead pages
import { DashboardPage } from "@/pages/admin/DashboardPage";
import { TeamQueuePage } from "@/pages/admin/TeamQueuePage";
import { AuditLogPage } from "@/pages/admin/AuditLogPage";
import { AuditEventDetailPage } from "@/pages/admin/AuditEventDetailPage";
import { UserManagementPage } from "@/pages/admin/UserManagementPage";
import { UserDetailPage } from "@/pages/admin/UserDetailPage";
import { KnowledgeManagementPage } from "@/pages/admin/KnowledgeManagementPage";
import { KnowledgeArticleDetailPage } from "@/pages/admin/knowledge/KnowledgeArticleDetailPage";
import { KnowledgeEditorPage } from "@/pages/admin/knowledge/KnowledgeEditorPage";
import { KnowledgeReviewQueuePage } from "@/pages/admin/knowledge/KnowledgeReviewQueuePage";
import { KnowledgeTaxonomyPage } from "@/pages/admin/knowledge/KnowledgeTaxonomyPage";
import { KnowledgeVersionHistoryPage } from "@/pages/admin/knowledge/KnowledgeVersionHistoryPage";
import { KnowledgeIndexingPage } from "@/pages/admin/knowledge/KnowledgeIndexingPage";
import { KnowledgeAnalyticsPage } from "@/pages/admin/knowledge/KnowledgeAnalyticsPage";
import { KnowledgeUploadPage } from "@/pages/admin/knowledge/KnowledgeUploadPage";
import { CandidateReviewPage } from "@/pages/admin/knowledge/CandidateReviewPage";
import { CandidateEditorPage } from "@/pages/admin/knowledge/CandidateEditorPage";
import { FeedbackReviewPage } from "@/pages/admin/FeedbackReviewPage";
import { AgentOperationsPage } from "@/pages/admin/AgentOperationsPage";
import { SpecialistReportPage } from "@/pages/admin/SpecialistReportPage";
import { TicketCategoriesPage } from "@/pages/admin/TicketCategoriesPage";

// ITSM workspace — Change Management + Inventory/Asset Management
import { ItsmLayout } from "@/features/itsm/ItsmLayout";
import { ItsmDashboard } from "@/features/itsm/ItsmDashboard";
import { ChangeListPage } from "@/features/itsm/changes/ChangeListPage";
import { ChangeFormPage } from "@/features/itsm/changes/ChangeFormPage";
import { ChangeDetailPage } from "@/features/itsm/changes/ChangeDetailPage";
import { ChangeTemplatesPage } from "@/features/itsm/changes/ChangeTemplatesPage";
import { ChangeCalendarPage } from "@/features/itsm/changes/ChangeCalendarPage";
import { ChangeBoardPage } from "@/features/itsm/changes/ChangeBoardPage";
import { AssetListPage } from "@/features/itsm/assets/AssetListPage";
import { AssetFormPage } from "@/features/itsm/assets/AssetFormPage";
import { AssetDetailPage } from "@/features/itsm/assets/AssetDetailPage";
import { AssetBoardPage } from "@/features/itsm/assets/AssetBoardPage";
import { AssetReportsPage } from "@/features/itsm/assets/AssetReportsPage";
import {
  AssetTypesPage,
  LocationsPage,
  VendorsPage,
} from "@/features/itsm/assets/ReferencePages";

function HomeRedirect() {
  const { user, isAuthenticated } = useAuthStore();
  if (!isAuthenticated || !user) return <Navigate to="/login" replace />;
  const defaultRoute = ROLE_ROUTES[user.role] || "/support";
  return <Navigate to={defaultRoute} replace />;
}

export function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/unauthorized" element={<UnauthorizedPage />} />

      {/* Home redirect based on role */}
      <Route path="/" element={<HomeRedirect />} />

      {/* Employee workspace (all authenticated users) */}
      <Route
        path="/support"
        element={
          <RouteGuard>
            <EmployeeLayout />
          </RouteGuard>
        }
      >
        <Route index element={<SupportChatPage />} />
        <Route path="chat" element={<SupportChatPage />} />
        {/* Live chat with an IT specialist — same component, role-aware UI. */}
        <Route path="live-chat/:sessionId" element={<LiveChatPage />} />
        <Route path="tickets" element={<MyTicketsPage />} />
        <Route path="tickets/:id" element={<TicketDetailPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>

      {/* IT Operations workspace (agents, leads, admins) */}
      <Route
        path="/operations"
        element={
          <ITStaffRoute>
            <OperationsLayout />
          </ITStaffRoute>
        }
      >
        <Route index element={<LiveQueuePage />} />
        <Route path="queue" element={<LiveQueuePage />} />
        <Route path="assigned" element={<AssignedTicketsPage />} />
        <Route path="live-chat/:sessionId" element={<LiveChatPage />} />
        <Route path="tickets/:id" element={<TicketWorkspacePage />} />
        <Route path="remote-assist" element={<RemoteAssistPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        <Route path="device-actions" element={<DeviceActionsPage />} />
      </Route>

      {/* Admin/Lead dashboard */}
      <Route
        path="/dashboard"
        element={
          <AdminRoute>
            <AdminLayout />
          </AdminRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="team-queue" element={<TeamQueuePage />} />
        <Route path="knowledge" element={<KnowledgeManagementPage />} />
        <Route path="knowledge/new" element={<KnowledgeEditorPage />} />
        <Route path="knowledge/review" element={<KnowledgeReviewQueuePage />} />
        <Route path="knowledge/taxonomy" element={<KnowledgeTaxonomyPage />} />
        <Route path="knowledge/indexing" element={<KnowledgeIndexingPage />} />
        <Route
          path="knowledge/analytics"
          element={<KnowledgeAnalyticsPage />}
        />
        <Route path="knowledge/:id" element={<KnowledgeArticleDetailPage />} />
        <Route path="knowledge/:id/edit" element={<KnowledgeEditorPage />} />
        <Route
          path="knowledge/:id/versions"
          element={<KnowledgeVersionHistoryPage />}
        />
        <Route path="knowledge/upload" element={<KnowledgeUploadPage />} />
        <Route
          path="knowledge/ingest/:jobId"
          element={<CandidateReviewPage />}
        />
        <Route
          path="knowledge/ingest/:jobId/:candidateId"
          element={<CandidateEditorPage />}
        />
        <Route path="users" element={<UserManagementPage />} />
        <Route path="users/:id" element={<UserDetailPage />} />
        <Route
          path="ticket-categories"
          element={
            <ITAdminRoute>
              <TicketCategoriesPage />
            </ITAdminRoute>
          }
        />
        <Route path="feedback/review" element={<FeedbackReviewPage />} />
        <Route path="agent-ops" element={<AgentOperationsPage />} />
        <Route path="reports/specialists" element={<SpecialistReportPage />} />
      </Route>

      {/* Changes + Assets — rendered inside the Admin Console shell so they
          share its sidebar, branding, and account menu. */}
      <Route
        path="/itsm"
        element={
          <AdminRoute>
            <AdminLayout />
          </AdminRoute>
        }
      >
        <Route element={<ItsmLayout />}>
          <Route index element={<ItsmDashboard />} />

          <Route path="changes" element={<ChangeListPage />} />
          <Route path="changes/new" element={<ChangeFormPage />} />
          <Route path="changes/calendar" element={<ChangeCalendarPage />} />
          <Route path="changes/board" element={<ChangeBoardPage />} />
          <Route path="changes/templates" element={<ChangeTemplatesPage />} />
          <Route path="changes/:id" element={<ChangeDetailPage />} />
          <Route path="changes/:id/edit" element={<ChangeFormPage />} />

          <Route path="assets" element={<AssetListPage />} />
          <Route path="assets/new" element={<AssetFormPage />} />
          <Route path="assets/board" element={<AssetBoardPage />} />
          <Route path="assets/types" element={<AssetTypesPage />} />
          <Route path="assets/locations" element={<LocationsPage />} />
          <Route path="assets/vendors" element={<VendorsPage />} />
          <Route path="assets/reports" element={<AssetReportsPage />} />
          <Route path="assets/:id" element={<AssetDetailPage />} />
          <Route path="assets/:id/edit" element={<AssetFormPage />} />
        </Route>
      </Route>

      {/* Audit (admin + auditor) */}
      <Route
        path="/audit"
        element={
          <AuditorRoute>
            <AdminLayout />
          </AuditorRoute>
        }
      >
        <Route index element={<AuditLogPage />} />
        <Route path=":eventId" element={<AuditEventDetailPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
