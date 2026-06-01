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
  shouldCaptureContext: boolean;
  searchQuery?: string;
  searchEngine?: string;
};

export type PageContext = {
  title: string;
  url: string;
  domain: string;
  metaDescription: string | null;
  headings: string[];
  selectedText: string | null;
  mainText: string;
  textChars: number;
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
