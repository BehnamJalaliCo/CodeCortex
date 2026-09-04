/** Declares its own sessionToken, unrelated to the authentication one. */
export function sessionToken(plan: string): string {
  const total = `سلام ${plan}`
  return `billing:${total}`
}

export function openPeriod(plan: string): string {
  return `${sessionToken(plan)}:open`
}
