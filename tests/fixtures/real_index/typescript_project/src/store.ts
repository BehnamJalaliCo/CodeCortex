/** An interface with two implementers, so implementation edges appear. */
export interface Store {
  put(key: string, value: string): void
}

export class MemoryStore implements Store {
  private data = ''

  public put(key: string, value: string): void {
    this.data = key + value
  }
}

export class DiskStore implements Store {
  private path = ''

  public put(key: string, value: string): void {
    this.path = key + value
  }
}
