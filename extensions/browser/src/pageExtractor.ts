import { domainFromUrl } from "./privacy.js";
import type { PageContext } from "./types";

export async function extractReadablePageContext(tabId: number | undefined, maxChars: number): Promise<PageContext> {
  if (!tabId) {
    return emptyContext();
  }
  return new Promise((resolve) => {
    chrome.scripting.executeScript<PageContext>(
      {
        target: { tabId },
        func: extractInPage,
        args: [Math.max(0, maxChars)],
      },
      (results) => {
        if (chrome.runtime?.lastError) {
          resolve(emptyContext());
          return;
        }
        resolve(results?.[0]?.result ?? emptyContext());
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
    context.mainText ? `Context excerpt:\n${context.mainText}` : "",
    context.selectedText ? `Selected text:\n${context.selectedText}` : "",
  ];
  return parts.filter(Boolean).join("\n\n");
}

function emptyContext(): PageContext {
  return {
    title: "",
    url: "",
    domain: "",
    metaDescription: null,
    headings: [],
    selectedText: null,
    mainText: "",
    textChars: 0,
  };
}

function extractInPage(limit: number): PageContext {
  const clone = document.body?.cloneNode(true) as HTMLElement | null;
  const title = document.title || "";
  const url = window.location.href;
  const domain = new URL(url).hostname;
  const metaDescription = document.querySelector<HTMLMetaElement>('meta[name="description"], meta[property="og:description"]')?.content?.trim() || null;
  const selection = window.getSelection?.();
  const selectedText = normalizeText(selection?.toString() || "").slice(0, Math.min(limit, 2000)) || null;

  if (!clone) {
    return { title, url, domain, metaDescription, headings: [], selectedText, mainText: "", textChars: 0 };
  }

  clone.querySelectorAll("script, style, noscript, svg, canvas, nav, footer, aside, header, form, input, textarea, select, button").forEach((node) => node.remove());

  const root =
    firstUsefulElement(clone, [
      "main",
      "article",
      '[role="main"]',
      ".prose",
      '[data-testid*="readme" i]',
      '[data-testid*="dataset" i]',
      '[data-testid*="model" i]',
      'div[class*="markdown" i]',
      'div[class*="prose" i]',
    ]) ?? clone;

  const headings = Array.from(root.querySelectorAll("h1, h2, h3"))
    .map((node) => normalizeText(node.textContent || ""))
    .filter(Boolean)
    .slice(0, 12);

  const candidates = Array.from(root.querySelectorAll("p, li, pre, code, table, h1, h2, h3, h4, section, div"))
    .filter(isVisibleElement)
    .map((node) => normalizeText(node.textContent || ""))
    .filter((text) => text.length > 30);

  const deduped: string[] = [];
  for (const text of candidates) {
    if (!deduped.some((existing) => existing === text || existing.includes(text))) {
      deduped.push(text);
    }
    if (deduped.join("\n\n").length >= limit) {
      break;
    }
  }
  const mainText = deduped.join("\n\n").slice(0, limit);
  return {
    title,
    url,
    domain,
    metaDescription,
    headings,
    selectedText,
    mainText,
    textChars: mainText.length,
  };
}

function firstUsefulElement(root: HTMLElement, selectors: string[]): HTMLElement | null {
  let best: HTMLElement | null = null;
  for (const selector of selectors) {
    const element = root.querySelector<HTMLElement>(selector);
    if (element && normalizeText(element.textContent || "").length > normalizeText(best?.textContent || "").length) {
      best = element;
    }
  }
  return best;
}

function isVisibleElement(element: Element): boolean {
  const htmlElement = element as HTMLElement;
  if (htmlElement.hidden || htmlElement.getAttribute("aria-hidden") === "true") {
    return false;
  }
  return true;
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function fallbackPageContext(title: string, url: string): PageContext {
  return {
    title,
    url,
    domain: domainFromUrl(url),
    metaDescription: null,
    headings: [],
    selectedText: null,
    mainText: "",
    textChars: 0,
  };
}
