import type { BrowserPickedFolder } from "./browserFolderPicker";
import type { BrowserFolderScanResult } from "./browserFolderScanner";

export const GMAIL_ATTACHMENT_MAX_TOTAL_BYTES = 20 * 1024 * 1024;
export const GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS = new Set([
  ".bat",
  ".cmd",
  ".db",
  ".dll",
  ".env",
  ".exe",
  ".key",
  ".pem",
  ".ps1",
  ".sh",
  ".sqlite",
]);

export type GmailAttachmentCandidate = {
  id: string;
  name: string;
  relativePath?: string;
  size: number;
  source: "manual" | "browser_folder" | "recent_task";
  reason: string;
  file?: File;
  selected: boolean;
  unavailableReason?: string;
};

export type GmailAttachmentIntent = {
  hasIntent: boolean;
  query: string;
  preferredExtensions: string[];
};

export function detectGmailAttachmentIntent(instruction: string): GmailAttachmentIntent {
  const text = instruction.toLowerCase();
  const hasIntent = /\b(attach|attached|attachment|resume|cv|pdf|report|summary|document|file)\b/.test(text);
  if (!hasIntent) return { hasIntent: false, query: "", preferredExtensions: [] };

  const preferredExtensions: string[] = [];
  if (/\b(pdf|report)\b/.test(text)) preferredExtensions.push(".pdf");
  if (/\b(resume|cv)\b/.test(text)) preferredExtensions.push(".pdf", ".docx", ".doc", ".txt");
  if (/\b(summary|markdown|md)\b/.test(text)) preferredExtensions.push(".md", ".txt", ".pdf");
  if (/\b(docx|word)\b/.test(text)) preferredExtensions.push(".docx");

  const query = text
    .replace(/\b(gmail|email|mail|send|draft|write|compose|to|with|attached|attach|attachment|please|my|the|a|an|new|latest|recent)\b/g, " ")
    .replace(/[^a-z0-9.\s_-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  return { hasIntent: true, query, preferredExtensions: [...new Set(preferredExtensions)] };
}

export async function findGmailAttachmentCandidates({
  intent,
  browserFolder,
  scanResult,
  recentTasks,
}: {
  intent: GmailAttachmentIntent;
  browserFolder: BrowserPickedFolder | null;
  scanResult: BrowserFolderScanResult | null;
  recentTasks: Array<{ title: string; outputFileName?: string; folderName?: string; type?: string; createdAt?: string }>;
}): Promise<GmailAttachmentCandidate[]> {
  if (!intent.hasIntent) return [];

  const candidates: GmailAttachmentCandidate[] = [];
  const seen = new Set<string>();

  if (scanResult) {
    const matches = rankScannedFiles(scanResult, intent).slice(0, 8);
    for (const file of matches) {
      const key = `scan:${file.relative_path}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const browserFile = browserFolder ? await tryGetBrowserFile(browserFolder.handle, file.relative_path) : null;
      candidates.push({
        id: key,
        name: file.name,
        relativePath: file.relative_path,
        size: browserFile?.size ?? file.size_bytes,
        source: "browser_folder",
        reason: browserFile ? "Found in selected folder." : "Found in scan. Choose it manually if needed.",
        file: browserFile ?? undefined,
        selected: Boolean(browserFile && matches.length === 1),
        unavailableReason: browserFile ? undefined : "Select this file manually to attach it.",
      });
    }
  }

  for (const task of recentTasks) {
    if (task.type !== "document_summary" || !task.outputFileName) continue;
    if (!matchesIntent(task.outputFileName, intent) && !/\b(summary|latest|recent)\b/.test(intent.query)) continue;
    const key = `task:${task.outputFileName}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const browserFile = browserFolder ? await tryGetBrowserFile(browserFolder.handle, task.outputFileName) : null;
    candidates.push({
      id: key,
      name: task.outputFileName,
      relativePath: task.outputFileName,
      size: browserFile?.size ?? 0,
      source: "recent_task",
      reason: browserFile ? `Recent summary output from ${task.folderName || browserFolder?.name || "Tasks"}.` : "Recent summary output. Choose it manually to attach it.",
      file: browserFile ?? undefined,
      selected: Boolean(browserFile),
      unavailableReason: browserFile ? undefined : "Select this file manually to attach it.",
    });
  }

  return dedupeCandidates(candidates).slice(0, 10);
}

export function candidatesFromManualFiles(files: File[]): GmailAttachmentCandidate[] {
  return files.map((file) => ({
    id: `manual:${file.name}:${file.size}:${file.lastModified}`,
    name: file.name,
    size: file.size,
    source: "manual",
    reason: "Selected manually.",
    file,
    selected: true,
  }));
}

export function validateGmailAttachments(candidates: GmailAttachmentCandidate[]) {
  const selected = selectedAttachmentFiles(candidates);
  const blocked = selected.filter((candidate) => GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS.has(extensionForName(candidate.name)));
  const totalBytes = selected.reduce((total, candidate) => total + candidate.size, 0);
  const warnings: string[] = [];
  if (blocked.length) warnings.push(`Remove blocked file type: ${blocked.map((item) => item.name).join(", ")}.`);
  if (totalBytes > GMAIL_ATTACHMENT_MAX_TOTAL_BYTES) warnings.push("Attachment total size is too large. Keep attachments under 20 MB.");
  return { ok: warnings.length === 0, warnings, totalBytes, selected };
}

export function selectedAttachmentFiles(candidates: GmailAttachmentCandidate[]) {
  return candidates.filter((candidate) => candidate.selected && candidate.file);
}

function rankScannedFiles(scanResult: BrowserFolderScanResult, intent: GmailAttachmentIntent) {
  return scanResult.files
    .map((file) => ({ file, score: scoreFile(file.name, file.relative_path, file.extension, intent) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.file);
}

function scoreFile(name: string, relativePath: string, extension: string, intent: GmailAttachmentIntent) {
  const haystack = `${name} ${relativePath}`.toLowerCase();
  let score = 0;
  if (intent.preferredExtensions.includes(extension.toLowerCase())) score += 4;
  for (const term of intent.query.split(/\s+/).filter((term) => term.length >= 2)) {
    if (haystack.includes(term)) score += term.length > 3 ? 3 : 1;
  }
  if (/\bresume|cv\b/.test(intent.query) && /\b(resume|cv)\b/.test(haystack)) score += 8;
  if (/\bsummary|latest|recent\b/.test(intent.query) && /summary/.test(haystack)) score += 6;
  return score;
}

function matchesIntent(filename: string, intent: GmailAttachmentIntent) {
  return scoreFile(filename, filename, extensionForName(filename), intent) > 0;
}

async function tryGetBrowserFile(rootHandle: FileSystemDirectoryHandle, relativePath: string): Promise<File | null> {
  try {
    const segments = normalizeRelativePath(relativePath);
    if (!segments.length) return null;
    let current = rootHandle;
    for (const segment of segments.slice(0, -1)) {
      current = await current.getDirectoryHandle(segment);
    }
    const fileHandle = await current.getFileHandle(segments[segments.length - 1]);
    return await fileHandle.getFile();
  } catch {
    return null;
  }
}

function normalizeRelativePath(path: string) {
  const segments = path.replace(/\\/g, "/").split("/").filter(Boolean);
  if (segments.some((segment) => segment === "." || segment === ".." || segment.includes(":"))) return [];
  return segments;
}

function dedupeCandidates(candidates: GmailAttachmentCandidate[]) {
  const byName = new Map<string, GmailAttachmentCandidate>();
  for (const candidate of candidates) {
    const key = `${candidate.name}:${candidate.size}`;
    const existing = byName.get(key);
    if (!existing || (!existing.file && candidate.file)) {
      byName.set(key, candidate);
    }
  }
  return [...byName.values()];
}

function extensionForName(name: string) {
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index).toLowerCase() : "";
}
