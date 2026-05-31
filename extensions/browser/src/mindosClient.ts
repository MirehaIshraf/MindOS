import type { BrowserRuntime, MindOSBrowserEvent } from "./types";

export class MindOSClient {
  constructor(private readonly backendUrl: string) {}

  async testConnection(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl()}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }

  async getRuntime(): Promise<BrowserRuntime> {
    const response = await fetch(`${this.baseUrl()}/connectors/browser/runtime`);
    if (!response.ok) {
      throw new Error(`Runtime check failed with status ${response.status}`);
    }
    return (await response.json()) as BrowserRuntime;
  }

  async sendHeartbeat(payload: {
    client_id: string;
    extension_version: string;
    browser: string;
    status: string;
  }): Promise<{ status: string; connector_enabled: boolean }> {
    const response = await fetch(`${this.baseUrl()}/connectors/browser/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`Heartbeat failed with status ${response.status}`);
    }
    return (await response.json()) as { status: string; connector_enabled: boolean };
  }

  async savePageEvent(event: MindOSBrowserEvent): Promise<string> {
    const response = await fetch(`${this.baseUrl()}/ingest/external`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event),
    });
    if (!response.ok) {
      let message = `Save failed with status ${response.status}`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) {
          message = body.detail;
        }
      } catch {
        // Keep the status message.
      }
      throw new Error(message);
    }
    const body = (await response.json()) as { event_id: string };
    return body.event_id;
  }

  private baseUrl(): string {
    return this.backendUrl.replace(/\/+$/, "");
  }
}
