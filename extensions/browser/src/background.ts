import { MindOSClient } from "./mindosClient.js";
import { extractReadablePageContext, fallbackPageContext, formatCapturedPageContent } from "./pageExtractor.js";
import { classifyPage, domainFromUrl, isBlockedUrl, isPrivateOrSensitiveUrl } from "./privacy.js";
import type { BrowserRuntime, BrowserSettings, ChromeTab, MindOSBrowserEvent, PageClassification, PageContext } from "./types";

const EXTENSION_VERSION = "0.1.0";
const SESSION_ID = crypto.randomUUID();
const RECENT_CACHE_KEY = "recentSmartCaptures";
const RUNTIME_POLL_MS = 15_000;
const HEARTBEAT_MS = 30_000;
const CAPTURE_DUPLICATE_MS = 30 * 60_000;
const SEARCH_DUPLICATE_MS = 10 * 60_000;
let currentRuntime: BrowserRuntime | null = null;
let runtimeCheckedAt = 0;
let heartbeatAt = 0;
let activeState: { tabId: number; url: string; title: string; completed: boolean; activatedAt: number } | null = null;
const dwellTimers = new Map<number, ReturnType<typeof setTimeout>>();

void refreshRuntimeAndEvaluate();
setInterval(() => void refreshRuntimeAndEvaluate(), RUNTIME_POLL_MS);

chrome.tabs.onActivated.addListener((activeInfo) => {
  chrome.tabs.get(activeInfo.tabId, (tab) => {
    updateActiveState(activeInfo.tabId, tab, tab.status === "complete");
  });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (activeState?.tabId !== tabId && !tab.active) {
    return;
  }
  if (changeInfo.url || changeInfo.status === "complete" || tab.title) {
    updateActiveState(tabId, tab, changeInfo.status === "complete" || tab.status === "complete");
  }
});

async function refreshRuntimeAndEvaluate(): Promise<void> {
  await getRuntime(true);
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (tab?.id) {
      updateActiveState(tab.id, tab, tab.status === "complete");
    }
  });
}

function updateActiveState(tabId: number, tab: ChromeTab, completed: boolean): void {
  if (!tab.url || isBlockedUrl(tab.url)) {
    debug("Skip blocked or empty URL", tab.url);
    return;
  }
  const urlChanged = activeState?.tabId !== tabId || activeState.url !== tab.url;
  activeState = {
    tabId,
    url: tab.url,
    title: tab.title ?? activeState?.title ?? "",
    completed,
    activatedAt: urlChanged ? Date.now() : (activeState?.activatedAt ?? Date.now()),
  };
  if (completed) {
    scheduleDwellEvaluation(activeState);
  }
}

function scheduleDwellEvaluation(state: NonNullable<typeof activeState>): void {
  const existing = dwellTimers.get(state.tabId);
  if (existing) {
    clearTimeout(existing);
  }
  const minimumSeconds = Math.max(currentRuntime?.minimum_active_seconds ?? 8, 1);
  const elapsed = Date.now() - state.activatedAt;
  const delay = Math.max(0, minimumSeconds * 1000 - elapsed);
  const timer = setTimeout(() => {
    void evaluateAndMaybeCapture(state.tabId, state.url, state.title);
  }, delay);
  dwellTimers.set(state.tabId, timer);
}

async function evaluateAndMaybeCapture(tabId: number, expectedUrl: string, title: string): Promise<void> {
  const settings = await getSettings();
  const runtime = await getRuntime(false);
  if (!runtime?.enabled || runtime.capture_mode !== "smart") {
    debug("Skip: browser connector not in smart mode", runtime?.status);
    return;
  }
  if (runtime.capture_important_pages !== true && runtime.capture_search_queries !== true) {
    debug("Skip: smart capture has no enabled event classes");
    return;
  }
  chrome.tabs.get(tabId, (tab) => {
    void evaluateLiveTab(tab, expectedUrl, title, runtime, settings);
  });
}

async function evaluateLiveTab(
  tab: ChromeTab,
  expectedUrl: string,
  title: string,
  runtime: BrowserRuntime,
  settings: BrowserSettings,
): Promise<void> {
  if (!tab.active || tab.url !== expectedUrl || !tab.url || isBlockedUrl(tab.url)) {
    debug("Skip: tab changed before dwell completed", tab.url);
    return;
  }
  const classification = classifyPage(tab.url, tab.title ?? title, runtime);
  debug("Smart capture evaluated URL", { url: tab.url, classification });
  if (isPrivateOrSensitiveUrl(tab.url) || classification.importance === "private") {
    debug("Skip: private/sensitive page");
    return;
  }
  const client = new MindOSClient(settings.backendUrl);
  try {
    await sendHeartbeatIfNeeded(client, settings);
    if (classification.searchQuery && runtime.capture_search_queries) {
      await sendSearchEventIfNeeded(client, settings, tab.url, classification);
      return;
    }
    if (classification.importance === "important" && runtime.capture_important_pages) {
      await sendCapturedEventIfNeeded(client, settings, runtime, tab, classification);
      return;
    }
    debug("Skip: page is not important enough for visible capture");
  } catch (error) {
    debug("Smart capture send failed", error instanceof Error ? error.message : error);
  }
}

async function sendSearchEventIfNeeded(
  client: MindOSClient,
  settings: BrowserSettings,
  url: string,
  classification: PageClassification,
): Promise<void> {
  const query = classification.searchQuery ?? "";
  const key = `browser_search_query:${classification.searchEngine ?? "search"}:${query.toLowerCase()}`;
  if (await wasRecentlySent(key, SEARCH_DUPLICATE_MS)) {
    debug("Skip duplicate search query", query);
    return;
  }
  await client.savePageEvent(buildSearchEvent(url, domainFromUrl(url), classification, settings));
  await markSent(key);
  debug("Smart capture sent search query", query);
}

async function sendCapturedEventIfNeeded(
  client: MindOSClient,
  settings: BrowserSettings,
  runtime: BrowserRuntime,
  tab: ChromeTab,
  classification: PageClassification,
): Promise<void> {
  if (!tab.url) {
    return;
  }
  const key = `browser_page_captured:${normalizeUrl(tab.url)}`;
  if (await wasRecentlySent(key, CAPTURE_DUPLICATE_MS)) {
    debug("Skip duplicate captured page", tab.url);
    return;
  }
  const maxChars = runtime.capture_full_page_text ? runtime.max_page_text_chars : Math.min(runtime.max_page_text_chars, 6000);
  const context = runtime.capture_page_context
    ? await extractReadablePageContext(tab.id, maxChars)
    : fallbackPageContext(tab.title ?? domainFromUrl(tab.url), tab.url);
  const event = buildCapturedEvent(tab.url, domainFromUrl(tab.url), tab.title ?? context.title, classification, context, settings, runtime);
  await client.savePageEvent(event);
  await markSent(key);
  debug("Smart capture sent captured page", { url: tab.url, textChars: context.textChars });
}

function buildSearchEvent(url: string, domain: string, classification: PageClassification, settings: BrowserSettings): MindOSBrowserEvent {
  const query = classification.searchQuery ?? "";
  return {
    source: "browser_extension",
    type: "browser_search_query",
    title: `Searched: ${query}`,
    content: `Search query: ${query}`,
    metadata: {
      query,
      search_engine: classification.searchEngine,
      url,
      domain,
      capture_mode: "smart",
      importance_reason: classification.reason,
      category: "search",
    },
    timestamp: null,
    client_id: settings.clientId,
    session_id: SESSION_ID,
  };
}

function buildCapturedEvent(
  url: string,
  domain: string,
  title: string,
  classification: PageClassification,
  context: PageContext,
  settings: BrowserSettings,
  runtime: BrowserRuntime,
): MindOSBrowserEvent {
  return {
    source: "browser_extension",
    type: "browser_page_captured",
    title: `Captured page: ${context.title || title || domain}`,
    content: formatCapturedPageContent(context, { title, url, domain }),
    metadata: {
      url,
      domain,
      page_title: context.title || title,
      capture_mode: "smart",
      importance_reason: classification.reason,
      category: classification.category,
      text_excerpt_included: Boolean(context.mainText),
      captured_text_chars: context.textChars,
      capture_full_page_text: runtime.capture_full_page_text,
      summary_status: "pending",
    },
    timestamp: null,
    client_id: settings.clientId,
    session_id: SESSION_ID,
  };
}

async function getRuntime(force: boolean): Promise<BrowserRuntime | null> {
  const now = Date.now();
  if (!force && currentRuntime && now - runtimeCheckedAt < RUNTIME_POLL_MS) {
    return currentRuntime;
  }
  const settings = await getSettings();
  const client = new MindOSClient(settings.backendUrl);
  try {
    currentRuntime = await client.getRuntime();
    runtimeCheckedAt = now;
    await sendHeartbeatIfNeeded(client, settings);
  } catch (error) {
    debug("Runtime unavailable", error instanceof Error ? error.message : error);
    currentRuntime = null;
  }
  return currentRuntime;
}

async function sendHeartbeatIfNeeded(client: MindOSClient, settings: BrowserSettings): Promise<void> {
  if (Date.now() - heartbeatAt < HEARTBEAT_MS) {
    return;
  }
  await client.sendHeartbeat({
    client_id: settings.clientId,
    extension_version: EXTENSION_VERSION,
    browser: browserName(),
    status: "active",
  });
  heartbeatAt = Date.now();
}

function getSettings(): Promise<BrowserSettings> {
  return new Promise((resolve) => {
    chrome.storage.local.get(defaultSettings(), (items) => {
      resolve(items as BrowserSettings);
    });
  });
}

async function wasRecentlySent(key: string, windowMs: number): Promise<boolean> {
  const cache = await recentCache();
  const lastSent = cache[key] ?? 0;
  return Date.now() - lastSent < windowMs;
}

async function markSent(key: string): Promise<void> {
  const cache = await recentCache();
  cache[key] = Date.now();
  await new Promise<void>((resolve) => chrome.storage.local.set({ [RECENT_CACHE_KEY]: cache }, resolve));
}

function recentCache(): Promise<Record<string, number>> {
  return new Promise((resolve) => {
    chrome.storage.local.get({ [RECENT_CACHE_KEY]: {} }, (items) => {
      resolve((items[RECENT_CACHE_KEY] as Record<string, number>) ?? {});
    });
  });
}

function normalizeUrl(url: string): string {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return url;
  }
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
  return navigator.userAgent.toLowerCase().includes("edg/") ? "edge" : "chrome";
}

function debug(message: string, details?: unknown): void {
  if (details === undefined) {
    console.debug(`[MindOS] ${message}`);
    return;
  }
  console.debug(`[MindOS] ${message}`, details);
}
