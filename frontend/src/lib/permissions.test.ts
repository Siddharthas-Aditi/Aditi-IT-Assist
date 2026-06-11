import { describe, expect, it } from 'vitest';

import {
  P,
  effectivePermissions,
  getDefaultRoute,
  hasPermission,
  isAdmin,
  isITStaff,
  isLeadOrAbove,
} from './permissions';

const user = (role: string) => ({ role: role as never, roles: [role as never] });

describe('permissions', () => {
  it('employee can read + give feedback but cannot author', () => {
    const u = user('employee');
    expect(hasPermission(u, P.KNOWLEDGE_READ)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_SUBMIT_FEEDBACK)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_CREATE)).toBe(false);
    expect(hasPermission(u, P.KNOWLEDGE_VIEW_INTERNAL)).toBe(false);
  });

  it('agent can author and submit for review but not publish', () => {
    const u = user('it_agent');
    expect(hasPermission(u, P.KNOWLEDGE_CREATE)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_SUBMIT_REVIEW)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_VIEW_INTERNAL)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_PUBLISH)).toBe(false);
    expect(hasPermission(u, P.KNOWLEDGE_REVIEW)).toBe(false);
  });

  it('lead can review, approve and publish but not reindex', () => {
    const u = user('it_lead');
    expect(hasPermission(u, P.KNOWLEDGE_APPROVE)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_PUBLISH)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_VIEW_ANALYTICS)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_REINDEX)).toBe(false);
  });

  it('admin can reindex and manage taxonomy', () => {
    const u = user('it_admin');
    expect(hasPermission(u, P.KNOWLEDGE_REINDEX)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_MANAGE_CATEGORIES)).toBe(true);
  });

  it('auditor has read-only internal access, no authoring', () => {
    const u = user('security_auditor');
    expect(hasPermission(u, P.KNOWLEDGE_VIEW_INTERNAL)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_CREATE)).toBe(false);
    expect(hasPermission(u, P.KNOWLEDGE_PUBLISH)).toBe(false);
  });

  it('explicit permission list overrides role derivation', () => {
    const u = { role: 'employee' as never, roles: ['employee' as never], permissions: [P.KNOWLEDGE_PUBLISH] };
    expect(hasPermission(u, P.KNOWLEDGE_PUBLISH)).toBe(true);
    expect(hasPermission(u, P.KNOWLEDGE_READ)).toBe(false);
  });

  it('role helpers classify correctly', () => {
    expect(isITStaff(user('it_agent'))).toBe(true);
    expect(isITStaff(user('employee'))).toBe(false);
    expect(isLeadOrAbove(user('it_lead'))).toBe(true);
    expect(isLeadOrAbove(user('it_agent'))).toBe(false);
    expect(isAdmin(user('it_admin'))).toBe(true);
  });

  it('default route follows highest privilege', () => {
    expect(getDefaultRoute(user('employee'))).toBe('/support');
    expect(getDefaultRoute(user('it_agent'))).toBe('/operations');
    expect(getDefaultRoute(user('it_admin'))).toBe('/dashboard');
  });

  it('effectivePermissions returns a set', () => {
    expect(effectivePermissions(user('it_admin')).size).toBeGreaterThan(5);
    expect(effectivePermissions(null).size).toBe(0);
  });
});
