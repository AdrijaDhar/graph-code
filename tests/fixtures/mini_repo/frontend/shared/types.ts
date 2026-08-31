export type User = { id: string };

export function describeUser(u: User): string {
  return u.id;
}
