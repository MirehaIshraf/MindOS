import { MindOSClient } from "./mindosClient.js";
import { extractReadablePageContext, fallbackPageContext, formatCapturedPageContent } from "./pageExtractor.js";
import { classifyPage, domainFromUrl, isBlockedUrl, normalizeSelection, shouldWarnForDomain } from "./privacy.js";
import type { BrowserPageInfo, BrowserRuntime, BrowserSettings, ChromeTab, MindOSBrowserEvent, PageClassification, PageContext } from "./types";

const EXTENSION_VERSION = "0.1.0";
const SESSION_ID = crypto.randomUUID();

const elements = {
  status: byId("status"),
  testConnection: byId<HTMLButtonElement>("testConnection"),
  mode: byId("mode"),
  classification: byId("classification"),
  classificationReason: byId("classificationReason"),
  pageTitle: byId("pageTitle"),
  pageDomain: byId("pageDomain"),
  pageUrl: byId("pageUrl"),
  warning: byId("warning"),
  selectionBlock: byId("selectionBlock"),
  selectionPreview: byId("selectionPreview"),
  note: byId<HTMLTextAreaElement>("note"),
  backendUrl: byId<HTMLInputElement>("backendUrl"),
  save: byId<HTMLButtonElement>("save"),
  capture: byId<HTMLButtonElement>("capture"),
  openSettings: byId<HTMLButtonElement>("openSettings"),
  message: byId("message"),
};

let settings: BrowserSettings;
let runtime: BrowserRuntime | null = null;
let pageInfo: BrowserPageInfo | null = null;
let pageClassification: PageClassification | null = null;
let selectedText = "";

void initialize();

async function initialize(): Promise<void> {
  settings = await getSettings();
  elements.backendUrl.value = settings.backendUrl;
  elements.backendUrl.addEventListener("change", () => void saveSettings());
  elements.testConnection.addEventListener("click", () => void testConnection(true));
  elements.save.addEventListener("click", () => void saveCurrentPage());
  elements.capture.addEventListener("click", () => void captureCurrentPage());
  elements.openSettings.addEventListener("click", () => chrome.tabs.create({ url: "http://localhost:5173/connectors" }));

  pageInfo = await getCurrentPage();
  renderPage(pageInfo);
  selectedText = pageInfo ? await getSelectedText(pageInfo) : "";
  renderSelection(selectedText);

  await refreshRuntime();
}

async function refreshRuntime(): Promise<void> {
  const client = new MindOSClient(settings.backendUrl);
  try {
    runtime = await client.getRuntime();
    await client.sendHeartbeat({
      client_id: settings.clientId,
      extension_version: EXTENSION_VERSION,
      browser: browserName(),
      status: "active",
    });
    renderStatus(runtime.enabled ? "Connected" : "Off");
  } catch {
    runtime = null;
    renderStatus("Offline");
  }
  renderClassification();
  updateSaveState();
}

async function saveCurrentPage(): Promise<void> {
  clearMessage();
  if (!pageInfo) {
    showMessage("No active page found.", "error");
    return;
  }
  if (isBlockedUrl(pageInfo.url)) {
    showMessage("This page type cannot be saved.", "error");
    return;
  }
  if (!runtime?.enabled) {
    showMessage("Browser connector is disabled in MindOS. Enable it from Connectors.", "error");
    return;
  }
  if (runtime.capture_mode === "off") {
    showMessage("Browser capture mode is off in MindOS.", "error");
    return;
  }
  if (shouldWarnForDomain(pageInfo.domain)) {
    const confirmed = window.confirm("This looks like a sensitive site. Save this page note to MindOS?");
    if (!confirmed) {
      return;
    }
  }

  elements.save.disabled = true;
  try {
    const note = elements.note.value.trim();
    const selection = settings.includeSelection ? normalizeSelection(selectedText, runtime.max_content_chars) : "";
    const context = await extractCurrentPageContext(runtime, selection);
    const event = buildEvent(pageInfo, note, selection, context);
    const eventId = await new MindOSClient(settings.backendUrl).savePageEvent(event);
    if (!context.mainText && runtime.capture_page_context) {
      showMessage(`Saved to MindOS (${eventId.slice(0, 8)}). Could not extract page text.`, "success");
      elements.note.value = "";
      return;
    }
    showMessage(`Saved to MindOS (${eventId.slice(0, 8)}).`, "success");
    elements.note.value = "";
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Could not save page.", "error");
  } finally {
    updateSaveState();
  }
}

async function captureCurrentPage(): Promise<void> {
  clearMessage();
  if (!pageInfo) {
    showMessage("No active page found.", "error");
    return;
  }
  if (!runtime?.enabled) {
    showMessage("Browser connector is disabled in MindOS. Enable it from Connectors.", "error");
    return;
  }
  if (runtime.capture_mode !== "smart") {
    showMessage("Smart capture is not enabled in MindOS.", "error");
    return;
  }
  if (isBlockedUrl(pageInfo.url)) {
    showMessage("This page type cannot be captured.", "error");
    return;
  }

  const classification = pageClassification ?? classifyPage(pageInfo.url, pageInfo.title, runtime);
  if (classification.importance === "private") {
    showMessage("This page is blocked by privacy rules.", "error");
    return;
  }

  elements.capture.disabled = true;
  try {
    const note = elements.note.value.trim();
    const selection = settings.includeSelection ? normalizeSelection(selectedText, runtime.max_content_chars) : "";
    const context = await extractCurrentPageContext(runtime, selection);
    const event = buildCapturedEvent(pageInfo, note, selection, classification, context);
    const eventId = await new MindOSClient(settings.backendUrl).savePageEvent(event);
    if (!context.mainText && runtime.capture_page_context) {
      showMessage(`Captured in MindOS (${eventId.slice(0, 8)}). Could not extract page text.`, "success");
      elements.note.value = "";
      return;
    }
    showMessage(`Captured in MindOS (${eventId.slice(0, 8)}).`, "success");
    elements.note.value = "";
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Could not capture page.", "error");
  } finally {
    updateSaveState();
  }
}

function buildEvent(info: BrowserPageInfo, note: string, selection: string, context: PageContext): MindOSBrowserEvent {
  const hasSelection = Boolean(selection);
  const content = formatCapturedPageContent(context, info, note);

  return {
    source: "browser_extension",
    type: hasSelection ? "browser_selection_saved" : "browser_page_saved",
    title: `Saved page: ${info.title || info.domain || info.url}`,
    content,
    metadata: {
      url: info.url,
      domain: info.domain,
      page_title: info.title,
      browser: browserName(),
      selected_text_included: hasSelection,
      user_note_included: Boolean(note),
      capture_mode: "manual",
      text_excerpt_included: Boolean(context.mainText),
      captured_text_chars: context.textChars,
    },
    timestamp: null,
    client_id: settings.clientId,
    session_id: SESSION_ID,
  };
}

function buildCapturedEvent(info: BrowserPageInfo, note: string, selection: string, classification: PageClassification, context: PageContext): MindOSBrowserEvent {
  const content = formatCapturedPageContent(context, info, note);

  return {
    source: "browser_extension",
    type: "browser_page_captured",
    title: `Captured page: ${info.title || info.domain || info.url}`,
    content,
    metadata: {
      url: info.url,
      domain: info.domain,
      page_title: info.title,
      browser: browserName(),
      selected_text_included: Boolean(selection),
      user_note_included: Boolean(note),
      capture_mode: "smart",
      importance_reason: classification.reason,
      category: classification.category,
      text_excerpt_included: Boolean(context.mainText),
      captured_text_chars: context.textChars,
      summary_status: "pending",
    },
    timestamp: null,
    client_id: settings.clientId,
    session_id: SESSION_ID,
  };
}

async function extractCurrentPageContext(runtime: BrowserRuntime, selection: string): Promise<PageContext> {
  if (!pageInfo) {
    return fallbackPageContext("", "");
  }
  if (!runtime.capture_page_context) {
    return { ...fallbackPageContext(pageInfo.title, pageInfo.url), selectedText: selection || null };
  }
  const tabId = await currentTabId();
  const context = await extractReadablePageContext(tabId, runtime.max_page_text_chars);
  return {
    ...(context.url ? context : fallbackPageContext(pageInfo.title, pageInfo.url)),
    selectedText: selection || context.selectedText,
  };
}

function currentTabId(): Promise<number | undefined> {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve(tabs[0]?.id));
  });
}

async function testConnection(showPopup: boolean): Promise<boolean> {
  settings = await getSettings();
  const connected = await new MindOSClient(settings.backendUrl).testConnection();
  if (showPopup) {
    showMessage(connected ? "Connected to MindOS." : `Could not connect to MindOS at ${settings.backendUrl}.`, connected ? "success" : "error");
  }
  return connected;
}

async function saveSettings(): Promise<void> {
  settings = { ...settings, backendUrl: elements.backendUrl.value.trim() || "http://localhost:8000" };
  await new Promise<void>((resolve) => chrome.storage.local.set(settings, resolve));
  await refreshRuntime();
}

function getSettings(): Promise<BrowserSettings> {
  return new Promise((resolve) => {
    chrome.storage.local.get(defaultSettings(), (items) => resolve(items as BrowserSettings));
  });
}

function getCurrentPage(): Promise<BrowserPageInfo | null> {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs: ChromeTab[]) => {
      const tab = tabs[0];
      if (!tab?.url) {
        resolve(null);
        return;
      }
      resolve({
        title: tab.title ?? "",
        url: tab.url,
        domain: domainFromUrl(tab.url),
      });
    });
  });
}

function getSelectedText(info: BrowserPageInfo): Promise<string> {
  if (!settings.includeSelection || isBlockedUrl(info.url)) {
    return Promise.resolve("");
  }
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs[0]?.id;
      if (!tabId) {
        resolve("");
        return;
      }
      chrome.scripting.executeScript<string>(
        {
          target: { tabId },
          func: () => window.getSelection()?.toString() ?? "",
        },
        (results) => {
          if (chrome.runtime?.lastError) {
            resolve("");
            return;
          }
          resolve(normalizeSelection(results?.[0]?.result ?? "", settings.maxContentChars));
        },
      );
    });
  });
}

function renderPage(info: BrowserPageInfo | null): void {
  if (!info) {
    elements.pageTitle.textContent = "No active page";
    elements.pageDomain.textContent = "";
    elements.pageUrl.textContent = "";
    return;
  }
  elements.pageTitle.textContent = info.title || "Untitled page";
  elements.pageDomain.textContent = info.domain;
  elements.pageUrl.textContent = info.url;
  if (isBlockedUrl(info.url)) {
    showWarning("This page type cannot be saved to MindOS.");
  } else if (shouldWarnForDomain(info.domain)) {
    showWarning("This may be a sensitive site. Review before saving.");
  }
}

function renderClassification(): void {
  const mode = runtime?.capture_mode ?? "offline";
  elements.mode.textContent = mode === "smart" ? "Smart" : mode === "manual" ? "Manual" : mode === "off" ? "Off" : "Offline";
  if (!pageInfo) {
    elements.classification.textContent = "Unknown";
    elements.classificationReason.textContent = "";
    return;
  }
  pageClassification = runtime ? classifyPage(pageInfo.url, pageInfo.title, runtime) : null;
  if (!pageClassification) {
    elements.classification.textContent = "Unknown";
    elements.classificationReason.textContent = "Connect to MindOS to classify the current page.";
    return;
  }
  elements.classification.textContent = pageClassification.importance.charAt(0).toUpperCase() + pageClassification.importance.slice(1);
  elements.classificationReason.textContent = pageClassification.reason;
}

function renderSelection(selection: string): void {
  if (!selection) {
    elements.selectionBlock.classList.add("hidden");
    return;
  }
  elements.selectionBlock.classList.remove("hidden");
  elements.selectionPreview.textContent = selection;
}

function renderStatus(label: "Connected" | "Off" | "Offline"): void {
  elements.status.textContent = label;
}

function updateSaveState(): void {
  elements.save.disabled = !pageInfo || !runtime?.enabled || runtime.capture_mode === "off" || isBlockedUrl(pageInfo.url);
  elements.capture.disabled = !pageInfo || !runtime?.enabled || isBlockedUrl(pageInfo.url) || runtime.capture_mode !== "smart" || pageClassification?.importance === "private";
}

function showWarning(message: string): void {
  elements.warning.textContent = message;
  elements.warning.classList.remove("hidden");
}

function showMessage(message: string, variant: "success" | "error"): void {
  elements.message.textContent = message;
  elements.message.className = `message ${variant}`;
}

function clearMessage(): void {
  elements.message.textContent = "";
  elements.message.className = "message";
}

function browserName(): string {
  return navigator.userAgent.toLowerCase().includes("edg/") ? "edge" : "chrome";
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

function byId<T extends HTMLElement = HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing element #${id}`);
  }
  return element as T;
}
