/** UI action gates that mirror the backend Change and Asset permission matrix. */

import { hasPermission, P, type PermissionCode } from "@/lib/permissions";
import type { AuthUser } from "@/types/auth";

export type ItsmAction =
  | "change:create"
  | "change:update"
  | "change:approve"
  | "change:implement"
  | "change:close"
  | "change:delete"
  | "asset:create"
  | "asset:update"
  | "asset:assign"
  | "asset:retire"
  | "asset:delete";

const ACTION_PERMISSION: Record<ItsmAction, PermissionCode> = {
  "change:create": P.CHANGE_CREATE,
  "change:update": P.CHANGE_UPDATE,
  "change:approve": P.CHANGE_APPROVE,
  "change:implement": P.CHANGE_IMPLEMENT,
  "change:close": P.CHANGE_CLOSE,
  "change:delete": P.CHANGE_DELETE,
  "asset:create": P.ASSET_CREATE,
  "asset:update": P.ASSET_UPDATE,
  "asset:assign": P.ASSET_ASSIGN,
  "asset:retire": P.ASSET_RETIRE,
  "asset:delete": P.ASSET_DELETE,
};

export function canPerformItsmAction(
  user: AuthUser | null | undefined,
  action: ItsmAction,
): boolean {
  return hasPermission(user, ACTION_PERMISSION[action]);
}
