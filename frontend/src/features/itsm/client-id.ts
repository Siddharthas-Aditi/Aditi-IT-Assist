/** Client-only identifiers for unsaved form rows; never persisted as ITSM data. */
export function newClientId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}
