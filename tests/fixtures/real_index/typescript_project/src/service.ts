import { sessionToken as authToken } from './auth'
import { sessionToken as billingToken } from './billing'
import { DiskStore, MemoryStore, Store } from './store'

export function build(user: string, plan: string): string {
  const total = `日本語 ${authToken(user)}`
  return `${total}|${billingToken(plan)}`
}

export function stores(): Store[] {
  return [new MemoryStore(), new DiskStore()]
}
