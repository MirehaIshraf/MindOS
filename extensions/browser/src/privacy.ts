const BLOCKED_SCHEMES = ["chrome:", "edge:", "about:", "file:"];
const WARNING_DOMAINS = [
  "mail.google.com",
  "accounts.google.com",
  "paypal.com",
  "stripe.com",
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
