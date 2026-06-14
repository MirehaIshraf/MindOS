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
  ".rar",
  ".sh",
  ".sqlite",
  ".zip",
  ".7z",
]);

export type AttachmentCandidate = {
  id: string;
  name: string;
  path?: string;
  relative_path?: string;
  source_id?: string;
  size_bytes: number;
  extension: string;
  source: "manual_picker" | "recent_task_output" | "selected_folder_scan" | "file_index";
  modified_at?: string;
  score: number;
  reason: string;
  selected: boolean;
  file?: File;
  unavailableReason?: string;
};

export type AttachmentIntent = {
  attachment_intent: boolean;
  file_query: string;
  extension_preference: string[];
  latest_preference: boolean;
};

export type RecentTaskOutput = {
  title: string;
  outputFileName?: string;
  folderName?: string;
  type?: string;
  createdAt?: string;
};

export type MemoryFileEvent = {
  name?: string;
  path?: string;
  relative_path?: string;
  size_bytes?: number;
  extension?: string;
  modified_at?: string;
  title?: string;
};

export function detectAttachmentIntent(instruction: string): AttachmentIntent {
  const text = instruction.toLowerCase();
  const hasPhrase =
    /\b(attach|attached|attachment)\b/.test(text) ||
    /\b(with|include|send|mail|email)\s+(my\s+|the\s+|this\s+|these\s+|latest\s+|recent\s+)?(cv|resume|report|pdf|document|file|files|thesis|project proposal|summary)\b/.test(text) ||
    /\b(send|mail|email)\s+(my\s+|the\s+)?(resume|cv|report|pdf|thesis|project proposal)\b/.test(text);

  if (!hasPhrase) {
    return { attachment_intent: false, file_query: "", extension_preference: [], latest_preference: false };
  }

  const extensionPreference = new Set<string>();
  if (/\b(resume|cv|curriculum vitae)\b/.test(text)) [".pdf", ".docx", ".doc"].forEach((extension) => extensionPreference.add(extension));
  if (/\b(pdf|report)\b/.test(text)) extensionPreference.add(".pdf");
  if (/\b(docx|word)\b/.test(text)) extensionPreference.add(".docx");
  if (/\b(markdown|md|summary)\b/.test(text)) extensionPreference.add(".md");
  if (/\b(txt|text)\b/.test(text)) extensionPreference.add(".txt");

  const queryTerms = new Set<string>();
  if (/\b(resume|cv|curriculum vitae)\b/.test(text)) {
    queryTerms.add("resume");
    queryTerms.add("cv");
    queryTerms.add("curriculum");
    queryTerms.add("vitae");
  }
  if (/\b(summary)\b/.test(text)) queryTerms.add("summary");
  if (/\b(report)\b/.test(text)) queryTerms.add("report");
  if (/\b(thesis)\b/.test(text)) queryTerms.add("thesis");
  if (/\b(project proposal)\b/.test(text)) {
    queryTerms.add("project");
    queryTerms.add("proposal");
  }

  const cleaned = text
    .replace(/\b(gmail|email|mail|send|draft|write|compose|to|with|attached|attach|attachment|please|my|the|a|an|new|latest|recent|include|this|these|files?|document)\b/g, " ")
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, " ")
    .replace(/[^a-z0-9.\s_-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  cleaned.split(/\s+/).filter((term) => term.length >= 3).forEach((term) => queryTerms.add(term));

  return {
    attachment_intent: true,
    file_query: [...queryTerms].join(" ").trim(),
    extension_preference: [...extensionPreference],
    latest_preference: /\b(latest|recent|newest)\b/.test(text),
  };
}

export function findAttachmentCandidates({
  query,
  extensionPreference,
  latestPreference,
  recentTaskOutputs,
  selectedFolderScan,
  memoryFileEvents = [],
}: {
  query: string;
  extensionPreference: string[];
  latestPreference: boolean;
  recentTaskOutputs: RecentTaskOutput[];
  selectedFolderScan: BrowserFolderScanResult | null;
  memoryFileEvents?: MemoryFileEvent[];
}): AttachmentCandidate[] {
  const candidates: AttachmentCandidate[] = [];

  for (const task of recentTaskOutputs) {
    if (task.type !== "document_summary" || !task.outputFileName) continue;
    const extension = extensionForName(task.outputFileName);
    const score = scoreCandidate({
      name: task.outputFileName,
      relativePath: task.outputFileName,
      extension,
      query,
      extensionPreference,
      latestPreference,
      sourceBoost: 6,
      modifiedAt: task.createdAt,
    });
    if (score <= 0) continue;
    candidates.push({
      id: `recent_task_output:${task.outputFileName}:${task.createdAt || ""}`,
      name: task.outputFileName,
      relative_path: task.outputFileName,
      size_bytes: 0,
      extension,
      source: "recent_task_output",
      modified_at: task.createdAt,
      score,
      reason: `Recent summary output${task.folderName ? ` from ${task.folderName}` : ""}.`,
      selected: false,
      unavailableReason: "Choose this file manually if it is not in the selected folder.",
    });
  }

  if (selectedFolderScan) {
    for (const file of selectedFolderScan.files) {
      const extension = (file.extension || extensionForName(file.name)).toLowerCase();
      const score = scoreCandidate({
        name: file.name,
        relativePath: file.relative_path,
        extension,
        query,
        extensionPreference,
        latestPreference,
        sourceBoost: 3,
        modifiedAt: file.modified_at ?? undefined,
      });
      if (score <= 0) continue;
      candidates.push({
        id: `selected_folder_scan:${file.relative_path}`,
        name: file.name,
        relative_path: file.relative_path,
        size_bytes: file.size_bytes,
        extension,
        source: "selected_folder_scan",
        modified_at: file.modified_at ?? undefined,
        score,
        reason: "Found in the selected folder scan.",
        selected: false,
      unavailableReason: "Select this file manually if MindOS cannot access it from the folder handle.",
      });
    }
  }

  for (const event of memoryFileEvents) {
    const name = event.name || event.title || event.relative_path || event.path || "";
    if (!name) continue;
    const extension = (event.extension || extensionForName(name)).toLowerCase();
    const relativePath = event.relative_path || event.path || name;
    const score = scoreCandidate({
      name,
      relativePath,
      extension,
      query,
      extensionPreference,
      latestPreference,
      sourceBoost: 1,
      modifiedAt: event.modified_at,
    });
    if (score <= 0) continue;
    candidates.push({
      id: `file_index:${relativePath}`,
      name,
      path: event.path,
      relative_path: event.relative_path,
      size_bytes: event.size_bytes ?? 0,
      extension,
      source: "file_index",
      modified_at: event.modified_at,
      score,
      reason: "Matched known file metadata.",
      selected: false,
    });
  }

  const ranked = dedupeCandidates(candidates).sort((a, b) => {
    if (latestPreference) {
      const timeDiff = timestamp(b.modified_at) - timestamp(a.modified_at);
      if (timeDiff) return timeDiff;
    }
    return b.score - a.score;
  });

  if (ranked.length) {
    const top = ranked[0];
    const runnerUp = ranked[1];
    if (top.score >= 12 && (!runnerUp || top.score - runnerUp.score >= 4)) {
      top.selected = true;
    }
  }

  return ranked.slice(0, 10);
}

export async function hydrateAttachmentCandidateFiles(
  candidates: AttachmentCandidate[],
  browserFolder: BrowserPickedFolder | null,
): Promise<AttachmentCandidate[]> {
  if (!browserFolder) return candidates;
  const hydrated: AttachmentCandidate[] = [];
  for (const candidate of candidates) {
    if (candidate.file || !candidate.relative_path || !["selected_folder_scan", "recent_task_output"].includes(candidate.source)) {
      hydrated.push(candidate);
      continue;
    }
    const file = await tryGetBrowserFile(browserFolder.handle, candidate.relative_path);
    hydrated.push(
      file
        ? {
            ...candidate,
            file,
            size_bytes: file.size,
            modified_at: new Date(file.lastModified).toISOString(),
            unavailableReason: undefined,
          }
        : candidate,
    );
  }
  return hydrated;
}

export function candidatesFromManualFiles(files: File[]): AttachmentCandidate[] {
  return files.map((file) => ({
    id: `manual_picker:${file.name}:${file.size}:${file.lastModified}`,
    name: file.name,
    size_bytes: file.size,
    extension: extensionForName(file.name),
    source: "manual_picker",
    modified_at: new Date(file.lastModified).toISOString(),
    score: 100,
    reason: "Selected manually.",
    file,
    selected: true,
  }));
}

export function validateAttachments(candidates: AttachmentCandidate[]) {
  const selected = selectedAttachmentCandidates(candidates);
  const blocked = selected.filter((candidate) => GMAIL_BLOCKED_ATTACHMENT_EXTENSIONS.has(extensionForName(candidate.name)));
  const unavailable = selected.filter((candidate) => !candidate.file && !isIndexedAttachmentCandidate(candidate));
  const totalBytes = selected.reduce((total, candidate) => total + candidate.size_bytes, 0);
  const warnings: string[] = [];
  if (blocked.length) warnings.push(`Remove blocked attachment: ${blocked[0].name}`);
  if (unavailable.length) warnings.push(`Choose this file manually before continuing: ${unavailable[0].name}`);
  if (totalBytes > GMAIL_ATTACHMENT_MAX_TOTAL_BYTES) warnings.push("Attachment total size exceeds 20 MB.");
  return { ok: warnings.length === 0, warnings, totalBytes, selected };
}

export function selectedAttachmentFiles(candidates: AttachmentCandidate[]) {
  return candidates.filter((candidate) => candidate.selected && candidate.file);
}

export function selectedAttachmentCandidates(candidates: AttachmentCandidate[]) {
  return candidates.filter((candidate) => candidate.selected);
}

export function selectedIndexedAttachments(candidates: AttachmentCandidate[]) {
  return selectedAttachmentCandidates(candidates)
    .filter(isIndexedAttachmentCandidate)
    .map((candidate) => ({ source_id: candidate.source_id as string, relative_path: candidate.relative_path as string }));
}

export function isIndexedAttachmentCandidate(candidate: AttachmentCandidate) {
  return candidate.source === "file_index" && Boolean(candidate.source_id && candidate.relative_path && !candidate.unavailableReason);
}

function scoreCandidate({
  name,
  relativePath,
  extension,
  query,
  extensionPreference,
  latestPreference,
  sourceBoost,
  modifiedAt,
}: {
  name: string;
  relativePath: string;
  extension: string;
  query: string;
  extensionPreference: string[];
  latestPreference: boolean;
  sourceBoost: number;
  modifiedAt?: string;
}) {
  const haystack = `${name} ${relativePath}`.toLowerCase();
  const terms = normalizeQueryTerms(query);
  let score = sourceBoost;

  if (extensionPreference.map((item) => item.toLowerCase()).includes(extension)) score += 5;
  for (const term of terms) {
    if (haystack === term || haystack.startsWith(`${term}.`)) score += 10;
    else if (haystack.includes(term)) score += term.length > 4 ? 4 : 2;
  }
  if (terms.some((term) => ["resume", "cv"].includes(term)) && /\b(resume|cv)\b/.test(haystack)) score += 10;
  if (terms.includes("summary") && /summary/.test(haystack)) score += 8;
  if (terms.includes("report") && /report/.test(haystack)) score += 6;
  if (terms.includes("proposal") && /proposal/.test(haystack)) score += 6;
  if (latestPreference && timestamp(modifiedAt)) score += 2;

  return score;
}

function normalizeQueryTerms(query: string) {
  const terms = new Set(query.toLowerCase().split(/\s+/).filter((term) => term.length >= 2));
  if (terms.has("resume") || terms.has("cv")) {
    terms.add("resume");
    terms.add("cv");
  }
  return [...terms];
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

function dedupeCandidates(candidates: AttachmentCandidate[]) {
  const byKey = new Map<string, AttachmentCandidate>();
  for (const candidate of candidates) {
    const key = `${candidate.name.toLowerCase()}:${candidate.size_bytes || candidate.relative_path || candidate.path || ""}`;
    const existing = byKey.get(key);
    if (!existing || candidate.score > existing.score || (!existing.file && candidate.file)) {
      byKey.set(key, candidate);
    }
  }
  return [...byKey.values()];
}

function extensionForName(name: string) {
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index).toLowerCase() : "";
}

function timestamp(value?: string) {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}
