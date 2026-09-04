/** Declares sessionToken, distinct from the identically named billing export. */
export function sessionToken(user: string): string {
  // The emoji sits on the same line as the reference, so the column of `user`
  // differs between UTF-8 bytes, UTF-16 code units, and code points.
  const total = `🚀 ${user}`
  return `auth:${total}`
}

export function revoke(user: string): string {
  return `${sessionToken(user)}:revoked`
}
