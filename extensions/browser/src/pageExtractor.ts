import { domainFromUrl } from "./privacy.js";
import type { ChromeTab, HardDomExtractionResult, PageContext, PageExtractionResult } from "./types";

const RESTRICTED_URL_PREFIXES = ["chrome://", "edge://", "about:", "file:", "chrome-extension://"];

export async function runHardDomExtractionTest(tabId: number): Promise<HardDomExtractionResult> {
  const tab = await getTab(tabId);
  const tabUrl = tab?.url ?? "";
  if (isRestrictedUrl(tabUrl)) {
    return {
      ok: false,
      title: tab?.title ?? "",
      url: tabUrl,
      readyState: "",
      bodyTextLength: 0,
      bodyPreview: "",
      documentElementTextLength: 0,
      hasBody: false,
      error: "restricted_url",
      tabId,
    };
  }

  return new Promise((resolve) => {
    chrome.scripting.executeScript<HardDomExtractionResult>(
      {
        target: { tabId },
        func: () => {
          try {
            const bodyText = document.body?.innerText || "";
            return {
              ok: bodyText.length > 0,
              title: document.title || "",
              url: location.href || "",
              readyState: document.readyState,
              bodyTextLength: bodyText.length,
              bodyPreview: bodyText.slice(0, 500),
              documentElementTextLength: document.documentElement?.innerText?.length || 0,
              hasBody: !!document.body,
              error: null,
            };
          } catch (err) {
            return {
              ok: false,
              title: "",
              url: location.href || "",
              readyState: document.readyState,
              bodyTextLength: 0,
              bodyPreview: "",
              documentElementTextLength: 0,
              hasBody: !!document.body,
              error: String(err),
            };
          }
        },
      },
      (injectionResults) => {
        const lastError = chrome.runtime?.lastError?.message;
        if (lastError) {
          resolve({
            ok: false,
            title: tab?.title ?? "",
            url: tabUrl,
            readyState: "",
            bodyTextLength: 0,
            bodyPreview: "",
            documentElementTextLength: 0,
            hasBody: false,
            error: lastError,
            tabId,
          });
          return;
        }
        resolve({
          ...(injectionResults?.[0]?.result ?? emptyHardDomResult(tabId, tabUrl)),
          tabId,
        });
      },
    );
  });
}

export async function extractReadablePageContext(tabIdOrMaxChars: number | undefined, maybeMaxChars?: number): Promise<PageContext> {
  const tabId = maybeMaxChars === undefined ? await activeTabId() : tabIdOrMaxChars;
  const maxChars = maybeMaxChars === undefined ? Number(tabIdOrMaxChars ?? 4000) : maybeMaxChars;
  console.debug("[MindOS] extraction started");

  if (!tabId) {
    return normalizeResult({
      ...emptyResult(),
      diagnostics: { error: "No active tab id.", reason: "missing_tab_id" },
    });
  }

  const hardDom = await runHardDomExtractionTest(tabId);
  if (!hardDom.ok || hardDom.bodyTextLength <= 0) {
    const result = normalizeResult({
      ...emptyResult(),
      title: hardDom.title,
      url: hardDom.url,
      domain: domainFromUrl(hardDom.url),
      diagnostics: {
        reason: hardDom.error === "restricted_url" ? "restricted_url" : "hard_dom_access_failed",
        hardDomOk: hardDom.ok,
        bodyTextLength: hardDom.bodyTextLength,
        documentElementTextLength: hardDom.documentElementTextLength,
        hasBody: hardDom.hasBody,
        readyState: hardDom.readyState,
        bodyPreview: hardDom.bodyPreview,
        error: hardDom.error,
        tabId,
        url: hardDom.url,
      },
    });
    console.debug("[MindOS] extraction failed hard DOM test", result.diagnostics);
    return result;
  }

  return new Promise((resolve) => {
    chrome.scripting.executeScript<PageExtractionResult>(
      {
        target: { tabId },
        args: [Math.max(0, maxChars), hardDom],
        func: (limit: number, hardDomResult: HardDomExtractionResult) => {
          try {
            const normalizeText = (value: string): string => value.replace(/\s+/g, " ").trim();
            const isHuggingFace = location.hostname.toLowerCase() === "huggingface.co";
            const noisyLines = new Set([
              "models",
              "datasets",
              "spaces",
              "buckets",
              "pricing",
              "website",
              "tasks",
              "huggingchat",
              "collections",
              "organizations",
              "community",
              "blog",
              "docs",
              "log in",
              "sign up",
              "follow",
              "like",
            ]);
            const cleanReadableText = (value: string): string => {
              const lines = value
                .split(/[\n\r]+|(?<=\.)\s+/)
                .map((line) => normalizeText(line))
                .filter((line) => line && !noisyLines.has(line.toLowerCase()));
              const deduped: string[] = [];
              for (const line of lines) {
                if (deduped[deduped.length - 1]?.toLowerCase() === line.toLowerCase()) {
                  continue;
                }
                deduped.push(line);
              }
              return deduped.join("\n").trim();
            };
            const cloneText = (element: HTMLElement | null): string => {
              if (!element) {
                return "";
              }
              const clone = element.cloneNode(true) as HTMLElement;
              clone
                .querySelectorAll("script, style, noscript, svg, canvas, form, input, textarea, select, button, nav, header, footer, aside")
                .forEach((node) => node.remove());
              return cleanReadableText(clone.innerText || clone.textContent || "");
            };
            const metaDescription =
              document.querySelector<HTMLMetaElement>('meta[name="description"]')?.content?.trim() ||
              document.querySelector<HTMLMetaElement>('meta[property="og:description"]')?.content?.trim() ||
              null;
            const headings = Array.from(document.querySelectorAll("h1, h2, h3"))
              .map((node) => normalizeText(node.textContent || ""))
              .filter(Boolean)
              .slice(0, 20);
            const selectors = isHuggingFace
              ? [
                  "main article",
                  "main .prose",
                  'main [class*="prose"]',
                  'main [class*="markdown"]',
                  'main [class*="model-card"]',
                  'main [class*="dataset-card"]',
                  'main [class*="ModelCard"]',
                  'main [class*="DatasetCard"]',
                  'main [class*="readme"]',
                  "main",
                  "article",
                  '[role="main"]',
                  ".prose",
                  ".markdown-body",
                  "body",
                ]
              : ["main", "article", '[role="main"]', ".prose", ".markdown-body", "body"];
            const candidates = selectors.map((selector) => {
              const text = cloneText(document.querySelector<HTMLElement>(selector));
              return { selector, length: text.length, text };
            });
            const candidateLengths = candidates.reduce<Record<string, number>>((lengths, candidate) => {
              lengths[candidate.selector] = candidate.length;
              return lengths;
            }, {});
            const best = candidates.reduce(
              (current, candidate) => (candidate.length > current.length ? candidate : current),
              { selector: null as string | null, length: 0, text: "" },
            );
            const selectedText = normalizeText(window.getSelection?.()?.toString() || "").slice(0, Math.max(0, Math.floor(limit / 2))) || null;
            const textExcerpt = best.text.slice(0, limit);
            const meaningfulLines = textExcerpt.split(/[.!?]\s+|\n+/).filter((line) => normalizeText(line).length > 20);
            const ok = textExcerpt.length >= 120 || meaningfulLines.length >= 3;
            return {
              ok,
              title: document.title || "",
              url: location.href || "",
              domain: location.hostname || "",
              metaDescription,
              headings,
              textExcerpt: ok ? textExcerpt : "",
              textChars: ok ? textExcerpt.length : 0,
              selectedText,
              extractor: isHuggingFace ? "huggingface" : "generic_visible_text",
              diagnostics: {
                reason: ok ? "generic_dom_text_extracted" : "no_meaningful_text_extracted",
                hardDomOk: hardDomResult.ok,
                bodyTextLength: hardDomResult.bodyTextLength,
                documentElementTextLength: hardDomResult.documentElementTextLength,
                hasBody: hardDomResult.hasBody,
                readyState: hardDomResult.readyState,
                bodyPreview: hardDomResult.bodyPreview,
                usedSelector: best.selector,
                selectedSelector: best.selector,
                candidateLengths,
                mainTextLength: candidates.find((candidate) => candidate.selector === "main")?.length ?? 0,
                articleTextLength: candidates.find((candidate) => candidate.selector === "article")?.length ?? 0,
                selectedTextLength: selectedText?.length ?? 0,
                headingsCount: headings.length,
                isHuggingFace,
                error: null,
              },
            };
          } catch (error) {
            return {
              ok: false,
              title: document.title || "",
              url: location.href || "",
              domain: location.hostname || "",
              metaDescription: null,
              headings: [],
              textExcerpt: "",
              textChars: 0,
              selectedText: null,
              extractor: "generic_visible_text",
              diagnostics: {
                reason: "generic_extraction_error",
                hardDomOk: hardDomResult.ok,
                bodyTextLength: hardDomResult.bodyTextLength,
                documentElementTextLength: hardDomResult.documentElementTextLength,
                hasBody: hardDomResult.hasBody,
                readyState: hardDomResult.readyState,
                bodyPreview: hardDomResult.bodyPreview,
                error: error instanceof Error ? error.message : String(error),
              },
            };
          }
        },
      },
      (injectionResults) => {
        const lastError = chrome.runtime?.lastError?.message;
        if (lastError) {
          const result = normalizeResult({
            ...emptyResult(),
            title: hardDom.title,
            url: hardDom.url,
            domain: domainFromUrl(hardDom.url),
            diagnostics: {
              reason: "execute_script_failed",
              hardDomOk: hardDom.ok,
              bodyTextLength: hardDom.bodyTextLength,
              documentElementTextLength: hardDom.documentElementTextLength,
              hasBody: hardDom.hasBody,
              readyState: hardDom.readyState,
              bodyPreview: hardDom.bodyPreview,
              error: lastError,
              tabId,
              url: hardDom.url,
            },
          });
          console.debug("[MindOS] extraction executeScript failed", result.diagnostics);
          resolve(result);
          return;
        }

        const result = normalizeResult(
          injectionResults?.[0]?.result ?? {
            ...emptyResult(),
            diagnostics: {
              reason: "missing_execute_script_result",
              hardDomOk: hardDom.ok,
              bodyTextLength: hardDom.bodyTextLength,
              documentElementTextLength: hardDom.documentElementTextLength,
              hasBody: hardDom.hasBody,
              readyState: hardDom.readyState,
              bodyPreview: hardDom.bodyPreview,
              error: "missing_execute_script_result",
              tabId,
              url: hardDom.url,
            },
          },
        );
        console.debug("[MindOS] extraction complete", {
          ok: result.ok,
          textChars: result.textChars,
          usedSelector: result.diagnostics.usedSelector,
          error: result.diagnostics.error,
        });
        resolve(result);
      },
    );
  });
}

export function formatCapturedPageContent(context: PageContext, fallback: { title: string; url: string; domain: string }, note = ""): string {
  const title = context.title || fallback.title || fallback.domain || fallback.url;
  const url = context.url || fallback.url;
  const domain = context.domain || fallback.domain;
  const parts = [
    `Page: ${title}`,
    `URL: ${url}`,
    `Domain: ${domain}`,
    note ? `Note:\n${note}` : "",
    context.metaDescription ? `Description:\n${context.metaDescription}` : "",
    context.headings.length ? `Headings:\n${context.headings.map((heading) => `- ${heading}`).join("\n")}` : "",
    context.ok && context.mainText ? `Readable context excerpt:\n${context.mainText}` : "Readable context excerpt:\nNo readable page text was extracted.",
    context.selectedText ? `Selected text:\n${context.selectedText}` : "",
  ];
  return parts.filter(Boolean).join("\n\n");
}

export function fallbackPageContext(title: string, url: string): PageContext {
  const domain = domainFromUrl(url);
  return normalizeResult({
    ...emptyResult(),
    title,
    url,
    domain,
    diagnostics: { reason: "capture_page_context_disabled_or_unavailable", usedSelector: null },
  });
}

function activeTabId(): Promise<number | undefined> {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve(tabs[0]?.id));
  });
}

function getTab(tabId: number): Promise<ChromeTab | null> {
  return new Promise((resolve) => {
    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime?.lastError) {
        resolve(null);
        return;
      }
      resolve(tab ?? null);
    });
  });
}

function isRestrictedUrl(url: string): boolean {
  return RESTRICTED_URL_PREFIXES.some((prefix) => url.toLowerCase().startsWith(prefix));
}

function emptyHardDomResult(tabId: number, url: string): HardDomExtractionResult {
  return {
    ok: false,
    title: "",
    url,
    readyState: "",
    bodyTextLength: 0,
    bodyPreview: "",
    documentElementTextLength: 0,
    hasBody: false,
    error: "missing_injection_result",
    tabId,
  };
}

function emptyResult(): PageExtractionResult {
  return {
    ok: false,
    title: "",
    url: "",
    domain: "",
    metaDescription: null,
    headings: [],
    textExcerpt: "",
    textChars: 0,
    selectedText: null,
    extractor: "generic_visible_text",
    diagnostics: { reason: "empty_result" },
  };
}

function normalizeResult(result: PageExtractionResult): PageContext {
  const textExcerpt = result.ok ? result.textExcerpt || "" : "";
  return {
    ...result,
    metaDescription: result.metaDescription ?? null,
    selectedText: result.selectedText ?? null,
    textExcerpt,
    mainText: textExcerpt,
    textChars: result.ok ? result.textChars ?? textExcerpt.length : 0,
    extractor: result.extractor ?? "generic_visible_text",
    diagnostics: result.diagnostics ?? { reason: "missing_diagnostics" },
  };
}
