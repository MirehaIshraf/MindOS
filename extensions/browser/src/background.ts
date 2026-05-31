import { MindOSClient } from "./mindosClient.js";
import type { BrowserSettings } from "./types";

const EXTENSION_VERSION = "0.1.0";

void sendStartupHeartbeat();

async function sendStartupHeartbeat(): Promise<void> {
  const settings = await getSettings();
  const client = new MindOSClient(settings.backendUrl);
  try {
    await client.sendHeartbeat({
      client_id: settings.clientId,
      extension_version: EXTENSION_VERSION,
      browser: browserName(),
      status: "active",
    });
  } catch {
    // Background heartbeat is best-effort and never captures browsing history.
  }
}

function getSettings(): Promise<BrowserSettings> {
  return new Promise((resolve) => {
    chrome.storage.local.get(defaultSettings(), (items) => {
      resolve(items as BrowserSettings);
    });
  });
}

function defaultSettings(): BrowserSettings {
  return {
    backendUrl: "http://localhost:8000",
    clientId: "browser-local",
    includeSelection: true,
    includePageText: false,
    maxContentChars: 4000,
  };
}

function browserName(): string {
  const agent = navigator.userAgent.toLowerCase();
  if (agent.includes("edg/")) {
    return "edge";
  }
  return "chrome";
}
