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
  max_content_chars: number;
};

export type BrowserPageInfo = {
  title: string;
  url: string;
  domain: string;
};

export type MindOSBrowserEvent = {
  source: "browser_extension";
  type: "browser_page_saved" | "browser_selection_saved" | "browser_research_note";
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
};

export type ChromeScriptingResult<T> = {
  result?: T;
};

export type ChromeLike = {
  tabs: {
    query(queryInfo: Record<string, unknown>, callback: (tabs: ChromeTab[]) => void): void;
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
