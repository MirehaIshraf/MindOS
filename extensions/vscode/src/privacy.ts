import * as path from "node:path";

const SENSITIVE_NAMES = new Set([".env", "id_rsa", "id_dsa"]);
const SENSITIVE_EXTENSIONS = new Set([".pem", ".key"]);
const SENSITIVE_CONTENT_MARKERS = [
  "-----BEGIN PRIVATE KEY-----",
  "-----BEGIN RSA PRIVATE KEY-----",
  "AWS_SECRET_ACCESS_KEY",
  "SECRET_KEY",
  "API_KEY=",
];

export function shouldIgnoreFile(filePath: string, excludeGlobs: string[]): boolean {
  const normalized = normalizePath(filePath);
  return isSensitiveFile(filePath) || excludeGlobs.some((glob) => globToRegExp(glob).test(normalized));
}

export function isSensitiveFile(filePath: string): boolean {
  const baseName = path.basename(filePath).toLowerCase();
  const ext = path.extname(filePath).toLowerCase();
  return SENSITIVE_NAMES.has(baseName) || SENSITIVE_EXTENSIONS.has(ext);
}

export function containsSensitiveContent(content: string): boolean {
  return SENSITIVE_CONTENT_MARKERS.some((marker) => content.includes(marker));
}

export function sanitizeTerminalCommand(command: string): string {
  return command
    .replace(/(api[_-]?key|token|password|secret)=\S+/gi, "$1=<redacted>")
    .replace(/(Authorization:\s*Bearer\s+)\S+/gi, "$1<redacted>");
}

function normalizePath(filePath: string): string {
  return filePath.replace(/\\/g, "/");
}

function globToRegExp(glob: string): RegExp {
  const normalized = normalizePath(glob);
  const escaped = normalized
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*\//g, "(?:.*/)?")
    .replace(/\*\*/g, ".*")
    .replace(/\*/g, "[^/]*");
  return new RegExp(`^${escaped}$`, "i");
}
