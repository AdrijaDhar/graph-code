import { describeUser, User } from "@shared/types";

export function loadUser(): User {
  return { id: "1" };
}

export function show(): string {
  return describeUser(loadUser());
}
