export type BrowserSettings = {
  backendUrl: string;
  clientId: string;
  includeSelection: boolean;
  includePageText: boolean;
  maxContentChars: number;
};

export type BrowserRuntime = {
  id: "browser";
  enabled: boolean;
  configured: boolean;
  status: string;
  accepted_event_types: string[];
  capture_mode: "manual" | string;
  capture_search_queries: boolean;
  capture_important_pages: boolean;
  capture_page_context: boolean;
  capture_full_page_text: boolean;
  max_page_text_chars: number;
  minimum_active_seconds: number;
  ignored_domains: string[];
  important_domains: string[];
  history_retention_days: number;
  max_content_chars: number;
};

export type BrowserPageInfo = {
  title: string;
  url: string;
  domain: string;
};

export type MindOSBrowserEvent = {
  source: "browser_extension";
  type:
    | "browser_page_saved"
    | "browser_selection_saved"
    | "browser_research_note"
    | "browser_page_seen"
    | "browser_search_query"
    | "browser_page_captured"
    | "browser_page_summary";
  title: string;
  content: string;
  metadata: Record<string, unknown>;
  timestamp: string | null;
  client_id: string;
  session_id: string;
};

export type ChromeTab = {
  id?: number;
  title?: string;
  url?: string;
  active?: boolean;
  windowId?: number;
  status?: string;
};

export type PageClassification = {
  importance: "important" | "normal" | "noisy" | "private";
  reason: string;
  category: string;
  pageType: "homepage" | "search" | "listing" | "content" | "action" | "unknown";
  pageTypeReason: string;
  shouldCaptureContext: boolean;
  searchQuery?: string;
  searchEngine?: string;
};

export type PageExtractionResult = {
  ok: boolean;
  title: string;
  url: string;
  domain: string;
  metaDescription?: string | null;
  headings: string[];
  textExcerpt: string;
  textChars: number;
  selectedText?: string | null;
  extractor: "generic_visible_text";
  diagnostics: {
    reason?: string;
    hardDomOk?: boolean;
    bodyTextLength?: number;
    documentElementTextLength?: number;
    hasBody?: boolean;
    readyState?: string;
    bodyPreview?: string;
    mainTextLength?: number;
    articleTextLength?: number;
    selectedTextLength?: number;
    usedSelector?: string | null;
    selectedSelector?: string | null;
    candidateLengths?: Record<string, number>;
    headingsCount?: number;
    tabId?: number;
    url?: string;
    error?: string | null;
  };
};

export type HardDomExtractionResult = {
  ok: boolean;
  title: string;
  url: string;
  readyState: string;
  bodyTextLength: number;
  bodyPreview: string;
  documentElementTextLength: number;
  hasBody: boolean;
  error: string | null;
  tabId?: number;
};

export type PageContext = PageExtractionResult & {
  mainText: string;
  metaDescription: string | null;
  selectedText: string | null;
};

export type ChromeScriptingResult<T> = {
  result?: T;
};

export type ChromeLike = {
  tabs: {
    query(queryInfo: Record<string, unknown>, callback: (tabs: ChromeTab[]) => void): void;
    get(tabId: number, callback: (tab: ChromeTab) => void): void;
    create(createProperties: { url: string }): void;
    onActivated: {
      addListener(callback: (activeInfo: { tabId: number; windowId: number }) => void): void;
    };
    onUpdated: {
      addListener(callback: (tabId: number, changeInfo: { status?: string; url?: string }, tab: ChromeTab) => void): void;
    };
  };
  scripting: {
    executeScript<T>(details: Record<string, unknown>, callback: (results: Array<ChromeScriptingResult<T>>) => void): void;
  };
  storage: {
    local: {
      get(keys: Record<string, unknown>, callback: (items: Record<string, unknown>) => void): void;
      set(items: Record<string, unknown>, callback?: () => void): void;
    };
  };
  runtime?: {
    lastError?: { message?: string };
  };
};

declare global {
  const chrome: ChromeLike;
}
