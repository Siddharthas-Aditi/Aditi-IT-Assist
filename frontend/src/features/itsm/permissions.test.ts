import { describe, expect, it } from "vitest";

import type { AuthUser } from "@/types/auth";

import { canPerformItsmAction, type ItsmAction } from "./permissions";

function user(role: AuthUser["role"]): AuthUser {
  return { id: role, email: `${role}@example.test`, full_name: role, role, roles: [role] };
}

const ACTIONS: ItsmAction[] = [
  "change:create", "change:approve", "change:implement", "change:close", "change:delete",
  "asset:create", "asset:assign", "asset:retire", "asset:delete",
];

describe("ITSM UI permission gates", () => {
  it("hides every Change and Asset write action from employees and auditors", () => {
    for (const role of ["employee", "security_auditor"] as const) {
      for (const action of ACTIONS) expect(canPerformItsmAction(user(role), action)).toBe(false);
    }
  });

  it("keeps approval, close, retirement, and deletion unavailable to IT agents", () => {
    const agent = user("it_agent");
    expect(canPerformItsmAction(agent, "change:create")).toBe(true);
    expect(canPerformItsmAction(agent, "change:implement")).toBe(true);
    expect(canPerformItsmAction(agent, "asset:create")).toBe(true);
    expect(canPerformItsmAction(agent, "asset:assign")).toBe(true);
    expect(canPerformItsmAction(agent, "change:approve")).toBe(false);
    expect(canPerformItsmAction(agent, "change:close")).toBe(false);
    expect(canPerformItsmAction(agent, "asset:retire")).toBe(false);
    expect(canPerformItsmAction(agent, "asset:delete")).toBe(false);
  });

  it("gives IT leads every operational action except change deletion", () => {
    const lead = user("it_lead");
    expect(canPerformItsmAction(lead, "change:create")).toBe(true);
    expect(canPerformItsmAction(lead, "change:approve")).toBe(true);
    expect(canPerformItsmAction(lead, "change:implement")).toBe(true);
    expect(canPerformItsmAction(lead, "change:close")).toBe(true);
    expect(canPerformItsmAction(lead, "change:delete")).toBe(false);
    expect(canPerformItsmAction(lead, "asset:retire")).toBe(true);
    expect(canPerformItsmAction(lead, "asset:delete")).toBe(true);
  });

  it("gives IT admins the full backend Change and Asset action set", () => {
    const admin = user("it_admin");
    for (const action of ACTIONS) expect(canPerformItsmAction(admin, action)).toBe(true);
  });
});
