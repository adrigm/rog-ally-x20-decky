export interface QueuedWrite {
  kind: string;
  target: string;
}

/** Serializes one control's writes, retaining the last pending value per kind. */
export class WriteQueue<T extends QueuedWrite> {
  private pending = new Map<string, T>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private disposed = false;
  private execute: (write: T) => Promise<void>;
  private delayMs: number;

  constructor(execute: (write: T) => Promise<void>, delayMs = 150) {
    this.execute = execute;
    this.delayMs = delayMs;
  }

  push(write: T): void {
    if (this.disposed) return;
    this.pending.set(write.kind, write);
    this.schedule();
  }

  flush(): void {
    if (this.disposed || this.running) return;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    void this.drain();
  }

  clear(): void {
    this.pending.clear();
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  dispose(): void {
    this.disposed = true;
    this.clear();
  }

  private schedule(): void {
    if (this.disposed || this.running || this.timer !== null || !this.pending.size) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.drain();
    }, this.delayMs);
  }

  private async drain(): Promise<void> {
    if (this.disposed || this.running) return;
    const entry = this.pending.entries().next();
    if (entry.done) return;
    const [kind, write] = entry.value;
    this.pending.delete(kind);
    this.running = true;
    try {
      await this.execute(write);
    } catch {
      // The controller reports failures; keep the queue usable after a rejected RPC.
    } finally {
      this.running = false;
      this.schedule();
    }
  }
}
