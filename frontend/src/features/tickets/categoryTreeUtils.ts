/** Pure helpers for ticket category tree admin UI. */

import type { TicketCategoryNode } from '@/lib/api';

export function filterActiveTree(nodes: TicketCategoryNode[]): TicketCategoryNode[] {
  return nodes
    .filter((n) => n.is_active)
    .map((n) => ({
      ...n,
      children: n.children?.length ? filterActiveTree(n.children) : [],
    }));
}

export function isLeaf(node: TicketCategoryNode): boolean {
  return !node.children?.length;
}

export function findByName(
  nodes: TicketCategoryNode[] | undefined,
  name: string,
): TicketCategoryNode | undefined {
  return nodes?.find((n) => n.name === name);
}
