import type { MindOSEvent, VSCodeRuntime } from "./types";

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

  async sendEvent(event: MindOSEvent): Promise<void> {
    const response = await fetch(`${this.baseUrl()}/ingest/external`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event),
    });
    if (!response.ok) {
      throw new Error(`MindOS ingest failed with status ${response.status}`);
    }
  }

  async getVSCodeRuntime(): Promise<VSCodeRuntime> {
    const response = await fetch(`${this.baseUrl()}/connectors/vscode/runtime`);
    if (!response.ok) {
      throw new Error(`MindOS runtime check failed with status ${response.status}`);
    }
    return (await response.json()) as VSCodeRuntime;
  }

  async sendVSCodeHeartbeat(payload: {
    client_id: string;
    extension_version: string;
    workspace_name?: string;
    workspace_folders: string[];
    session_id: string;
    status: string;
  }): Promise<{ status: string; connector_enabled: boolean }> {
    const response = await fetch(`${this.baseUrl()}/connectors/vscode/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`MindOS heartbeat failed with status ${response.status}`);
    }
    return (await response.json()) as { status: string; connector_enabled: boolean };
  }

  async sendBulkEvents(events: MindOSEvent[]): Promise<void> {
    if (events.length === 0) {
      return;
    }
    const response = await fetch(`${this.baseUrl()}/ingest/external/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    if (!response.ok) {
      throw new Error(`MindOS bulk ingest failed with status ${response.status}`);
    }
  }

  async toggleConnector(connectorId: "vscode", enabled: boolean): Promise<void> {
    const response = await fetch(`${this.baseUrl()}/connectors/${connectorId}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!response.ok) {
      throw new Error(`MindOS connector toggle failed with status ${response.status}`);
    }
  }

  private baseUrl(): string {
    return this.backendUrl.replace(/\/+$/, "");
  }
}
