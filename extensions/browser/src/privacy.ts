import type { PageClassification } from "./types";

const BLOCKED_SCHEMES = ["chrome:", "edge:", "about:", "file:"];
const PRIVATE_DOMAINS = [
  "mail.google.com",
  "accounts.google.com",
  "paypal.com",
  "stripe.com",
  "web.whatsapp.com",
];
const NOISY_DOMAINS = [
  "youtube.com",
  "facebook.com",
  "instagram.com",
  "x.com",
  "twitter.com",
  "netflix.com",
  "spotify.com",
];
const IMPORTANT_DOMAINS = [
  "github.com",
  "gitlab.com",
  "bitbucket.org",
  "stackoverflow.com",
  "stackexchange.com",
  "readthedocs.io",
  "dev.to",
  "arxiv.org",
  "scholar.google.com",
  "patents.google.com",
  "huggingface.co",
  "ollama.com",
  "platform.openai.com",
  "docs.anthropic.com",
  "pytorch.org",
  "tensorflow.org",
  "kubernetes.io",
  "docs.docker.com",
  "cloud.google.com",
  "aws.amazon.com",
  "learn.microsoft.com",
  "azure.microsoft.com",
  "atlassian.net",
  "linear.app",
];
const IMPORTANT_KEYWORDS = [
  "api",
  "docs",
  "documentation",
  "error",
  "exception",
  "github",
  "pull request",
  "issue",
  "jira",
  "ticket",
  "patent",
  "arxiv",
  "paper",
  "research",
  "webrtc",
  "fastapi",
  "chromadb",
  "ollama",
  "embedding",
  "llm",
  "security",
  "auth",
  "jwt",
  "docker",
  "kubernetes",
  "aws",
  "azure",
];
const WARNING_DOMAINS = [
  ...PRIVATE_DOMAINS,
  "bank",
  "billing",
  "payment",
];

export function isBlockedUrl(url: string): boolean {
  const lower = url.toLowerCase();
  return BLOCKED_SCHEMES.some((scheme) => lower.startsWith(scheme));
}

export function shouldWarnForDomain(domain: string): boolean {
  const lower = domain.toLowerCase();
  return WARNING_DOMAINS.some((marker) => lower.includes(marker));
}

export function isPrivateOrSensitiveUrl(url: string, domain = domainFromUrl(url)): boolean {
  const lowerUrl = url.toLowerCase();
  const lowerDomain = domain.toLowerCase();
  if (isBlockedUrl(url)) {
    return true;
  }
  if (PRIVATE_DOMAINS.some((marker) => lowerDomain.includes(marker))) {
    return true;
  }
  return ["login", "signin", "sign-in", "checkout", "billing", "payment", "bank"].some((marker) => lowerUrl.includes(marker));
}

export function normalizeSelection(value: string, maxChars: number): string {
  return value.trim().replace(/\s+/g, " ").slice(0, Math.max(0, maxChars));
}

export function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export function classifyPage(url: string, title: string, runtime?: {
  ignored_domains?: string[];
  important_domains?: string[];
}): PageClassification {
  const domain = domainFromUrl(url);
  const text = `${url} ${title}`.toLowerCase();
  const lowerDomain = domain.toLowerCase();
  const search = extractSearchQuery(url);
  const pageType = classifyPageType(url, title);
  if (isPrivateOrSensitiveUrl(url, domain)) {
    return { importance: "private", reason: "Sensitive/login/payment page.", category: "private", ...pageType, shouldCaptureContext: false };
  }
  if ((runtime?.ignored_domains ?? []).some((marker) => lowerDomain.includes(marker.toLowerCase()))) {
    return { importance: "noisy", reason: "Domain is ignored in MindOS.", category: "unknown", ...pageType, shouldCaptureContext: false };
  }
  if (search.query) {
    return { importance: "normal", reason: "Search query detected.", category: "search", pageType: "search", pageTypeReason: "Search URL.", shouldCaptureContext: false, searchQuery: search.query, searchEngine: search.engine };
  }
  if (NOISY_DOMAINS.some((marker) => lowerDomain.includes(marker))) {
    return { importance: "noisy", reason: "Noisy or entertainment domain.", category: "entertainment", ...pageType, shouldCaptureContext: false };
  }
  const huggingFaceCategory = huggingFacePageCategory(url, lowerDomain);
  if (huggingFaceCategory) {
    return { importance: "important", reason: "Hugging Face AI/model/dataset page.", category: huggingFaceCategory, ...pageType, shouldCaptureContext: true };
  }
  if ((runtime?.important_domains ?? []).some((marker) => lowerDomain.includes(marker.toLowerCase()))) {
    return { importance: "important", reason: "Domain is marked important in MindOS.", category: "research", ...pageType, shouldCaptureContext: true };
  }
  if (IMPORTANT_DOMAINS.some((marker) => lowerDomain.includes(marker)) || lowerDomain.startsWith("docs.") || lowerDomain.startsWith("developer.")) {
    return { importance: "important", reason: "Developer/research domain.", category: categoryForDomain(lowerDomain), ...pageType, shouldCaptureContext: true };
  }
  if (IMPORTANT_KEYWORDS.some((keyword) => text.includes(keyword))) {
    return { importance: "important", reason: "Developer/research keyword.", category: "research", ...pageType, shouldCaptureContext: true };
  }
  return { importance: "normal", reason: "No strong work/research signal.", category: "unknown", ...pageType, shouldCaptureContext: false };
}

export function extractSearchQuery(url: string): { query?: string; engine?: string } {
  try {
    const parsed = new URL(url);
    const query = parsed.searchParams.get("q")?.trim();
    if (!query) {
      return {};
    }
    const host = parsed.hostname;
    if (host.includes("google.") && parsed.pathname.startsWith("/search")) return { query, engine: "google" };
    if (host.includes("bing.com") && parsed.pathname.startsWith("/search")) return { query, engine: "bing" };
    if (host.includes("duckduckgo.com")) return { query, engine: "duckduckgo" };
    if (host.includes("search.brave.com")) return { query, engine: "brave" };
    return {};
  } catch {
    return {};
  }
}

function categoryForDomain(domain: string): string {
  if (domain.includes("github") || domain.includes("gitlab") || domain.includes("bitbucket")) return "github";
  if (domain.includes("stackoverflow") || domain.includes("stackexchange")) return "stackoverflow";
  if (domain.includes("patent")) return "patent";
  if (domain.includes("arxiv") || domain.includes("scholar") || domain.includes("ieee") || domain.includes("acm")) return "research";
  if (domain.includes("openai") || domain.includes("anthropic") || domain.includes("huggingface") || domain.includes("ollama")) return "ai";
  if (domain.includes("aws") || domain.includes("azure") || domain.includes("cloud.google")) return "cloud";
  return "docs";
}

function huggingFacePageCategory(url: string, domain: string): string | null {
  if (!domain.includes("huggingface.co")) {
    return null;
  }
  try {
    const path = new URL(url).pathname.toLowerCase();
    if (path.startsWith("/datasets/")) return "ai_dataset";
    if (path.startsWith("/models/")) return "ai_model";
    if (path.startsWith("/spaces/")) return "ai";
    if (path.startsWith("/papers/")) return "research";
    if (path.startsWith("/docs/")) return "ai_docs";
    return "ai";
  } catch {
    return "ai";
  }
}

function classifyPageType(url: string, title: string): Pick<PageClassification, "pageType" | "pageTypeReason"> {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.toLowerCase().replace(/\/+$/, "");
    const domain = parsed.hostname.toLowerCase();
    const text = `${path} ${title}`.toLowerCase();
    if (!path || path === "") {
      return { pageType: "homepage", pageTypeReason: "Root domain." };
    }
    if (extractSearchQuery(url).query) {
      return { pageType: "search", pageTypeReason: "Search URL." };
    }
    if (domain.includes("huggingface.co") && /^\/(datasets|models|spaces|papers|docs)\/[^/]+\/[^/]+/.test(path)) {
      return { pageType: "content", pageTypeReason: "Hugging Face content page." };
    }
    if (domain.includes("patents.google.com") && path.startsWith("/patent/")) {
      return { pageType: "content", pageTypeReason: "Patent content page." };
    }
    if (domain.includes("github.com")) {
      if (/\/(issues|pull)\/\d+/.test(path)) return { pageType: "action", pageTypeReason: "GitHub issue or pull request." };
      if (/\/(issues|pulls|actions|projects)$/.test(path)) return { pageType: "listing", pageTypeReason: "GitHub listing page." };
      if (path.split("/").filter(Boolean).length >= 2) return { pageType: "content", pageTypeReason: "GitHub repository/content page." };
    }
    if (text.includes("dashboard") || text.includes("feed") || text.includes("explore") || text.includes("browse")) {
      return { pageType: "listing", pageTypeReason: "Listing/dashboard page." };
    }
    return { pageType: "content", pageTypeReason: "Readable page URL." };
  } catch {
    return { pageType: "unknown", pageTypeReason: "Could not parse URL." };
  }
}
