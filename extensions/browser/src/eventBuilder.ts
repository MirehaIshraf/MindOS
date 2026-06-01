import { formatCapturedPageContent } from "./pageExtractor.js";
import type { BrowserPageInfo, BrowserRuntime, BrowserSettings, MindOSBrowserEvent, PageClassification, PageContext } from "./types";

type BuildBrowserCapturedPageEventInput = {
  info: BrowserPageInfo;
  context: PageContext;
  settings: BrowserSettings;
  sessionId: string;
  captureMode: "manual" | "smart";
  classification?: PageClassification | null;
  runtime?: BrowserRuntime | null;
  note?: string;
  selectedText?: string;
  manualCapture?: boolean;
  eventType?: "browser_page_saved" | "browser_selection_saved" | "browser_page_captured";
};

export function buildBrowserCapturedPageEvent(input: BuildBrowserCapturedPageEventInput): MindOSBrowserEvent {
  const { info, context, settings, sessionId, captureMode, classification, runtime, note = "", selectedText = "" } = input;
  const hasExtractedText = context.ok && context.textChars > 0;
  const hasSelection = Boolean(selectedText);
  const eventType = input.eventType ?? (captureMode === "smart" ? "browser_page_captured" : hasSelection ? "browser_selection_saved" : "browser_page_saved");
  const titlePrefix = eventType === "browser_page_captured" ? "Captured page" : "Saved page";

  return {
    source: "browser_extension",
    type: eventType,
    title: `${titlePrefix}: ${context.title || info.title || info.domain || info.url}`,
    content: formatCapturedPageContent(context, info, note),
    metadata: {
      url: info.url,
      domain: info.domain,
      page_title: context.title || info.title,
      browser: browserName(),
      selected_text_included: hasSelection,
      user_note_included: Boolean(note),
      capture_mode: captureMode,
      manual_capture: input.manualCapture ?? captureMode === "manual",
      importance_reason: classification?.reason,
      category: classification?.category,
      page_type: classification?.pageType ?? "unknown",
      page_type_reason: classification?.pageTypeReason ?? (captureMode === "manual" ? "Manual capture." : "Smart capture."),
      meta_description: context.metaDescription,
      headings: context.headings,
      headings_count: context.headings.length,
      text_excerpt_included: hasExtractedText,
      captured_text_chars: hasExtractedText ? context.textChars : 0,
      capture_full_page_text: runtime?.capture_full_page_text ?? false,
      extractor: context.extractor,
      page_context_missing: !hasExtractedText,
      extraction_diagnostics: context.diagnostics,
    },
    timestamp: null,
    client_id: settings.clientId,
    session_id: sessionId,
  };
}

function browserName(): string {
  return navigator.userAgent.toLowerCase().includes("edg/") ? "edge" : "chrome";
}
