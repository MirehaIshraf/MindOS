import { MindOSClient } from "./mindosClient";
import type { MindOSEvent, QueueFlushResult } from "./types";

const MAX_QUEUE_SIZE = 500;

export class EventQueue {
  private readonly events: MindOSEvent[] = [];

  enqueue(event: MindOSEvent): void {
    this.events.push(event);
    while (this.events.length > MAX_QUEUE_SIZE) {
      this.events.shift();
    }
  }

  size(): number {
    return this.events.length;
  }

  async flushQueue(client: MindOSClient): Promise<QueueFlushResult> {
    const pending = this.events.splice(0, this.events.length);
    if (pending.length === 0) {
      return { sent: 0, failed: 0, remaining: 0 };
    }

    try {
      await client.sendBulkEvents(pending);
      return { sent: pending.length, failed: 0, remaining: this.events.length };
    } catch {
      for (const event of pending) {
        this.enqueue(event);
      }
      return { sent: 0, failed: pending.length, remaining: this.events.length };
    }
  }
}
