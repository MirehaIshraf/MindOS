import { getFileHandleByRelativePath } from "./browserFileExecutor";
import { truncateExtractedText, type DocumentTextExtractionResult } from "./documentExtractors/types";
import type { FileSnapshotItem } from "../types";
import type { BrowserFolderScanResult } from "./browserFolderScanner";

const TEXT_EXTENSIONS = new Set([".txt", ".md", ".log", ".json", ".csv"]);
const READABLE_EXTENSIONS = new Set([...TEXT_EXTENSIONS, ".pdf", ".docx"]);
const BLOCKED_EXTENSIONS = new Set([".env", ".pem", ".key", ".db", ".sqlite", ".exe", ".dll", ".zip"]);
const BLOCKED_SEGMENTS = new Set(["node_modules", ".git"]);

export type DocumentReadOptions = {
  instruction?: string;
  selectedFiles?: FileSnapshotItem[];
  maxFilesToRead?: number;
  maxFileSizeMb?: number;
  maxTotalChars?: number;
  maxCharsPerFile?: number;
  onProgress?: (message: string) => void;
};

export type ReadDocumentFile = {
  name: string;
  relative_path: string;
  extension: string;
  file_type: DocumentTextExtractionResult["file_type"];
  size_bytes: number;
  chars_read: number;
  page_count?: number;
  extraction_warnings: string[];
  text_excerpt_or_text: string;
};

export type BrowserDocumentReadResult = {
  files_read: ReadDocumentFile[];
  skipped: Array<{ relative_path: string; reason: string }>;
  total_chars: number;
  warnings: string[];
};

export function getReadableFilesFromScan(scanResult: BrowserFolderScanResult, instruction = ""): {
  candidates: FileSnapshotItem[];
  skipped: Array<{ relative_path: string; reason: string }>;
  warning?: string;
} {
  const requestedExtensions = requestedExtensionsFromInstruction(instruction);
  const skipped: Array<{ relative_path: string; reason: string }> = [];
  const candidates: FileSnapshotItem[] = [];

  for (const file of scanResult.files) {
    const extension = file.extension.toLowerCase();
    const relative = normalizeRelative(file.relative_path);
    if (file.name === ".env" || file.name.endsWith(".pem") || file.name.endsWith(".key")) {
      skipped.push({ relative_path: file.relative_path, reason: "Skipped sensitive file type." });
      continue;
    }
    if (isBlockedPath(relative)) {
      skipped.push({ relative_path: file.relative_path, reason: "Skipped protected or dependency path." });
      continue;
    }
    if (requestedExtensions.length && !requestedExtensions.includes(extension)) {
      skipped.push({ relative_path: file.relative_path, reason: "Does not match requested document type." });
      continue;
    }
    if (BLOCKED_EXTENSIONS.has(extension)) {
      skipped.push({ relative_path: file.relative_path, reason: "Blocked file type." });
      continue;
    }
    if (!READABLE_EXTENSIONS.has(extension)) {
      skipped.push({ relative_path: file.relative_path, reason: "Unsupported file type." });
      continue;
    }
    candidates.push(file);
  }

  return { candidates, skipped };
}

export async function readTextFileFromHandle(
  rootHandle: FileSystemDirectoryHandle,
  relativePath: string,
  limits: Required<Pick<DocumentReadOptions, "maxFileSizeMb" | "maxCharsPerFile">>,
): Promise<ReadDocumentFile> {
  const fileHandle = await getFileHandleByRelativePath(rootHandle, relativePath);
  const file = await fileHandle.getFile();
  const maxBytes = limits.maxFileSizeMb * 1024 * 1024;
  if (file.size > maxBytes) throw new Error(`File is larger than ${limits.maxFileSizeMb} MB.`);
  const extraction = await extractTextFromBrowserFile(file, limits.maxCharsPerFile);
  if (!extraction.ok) throw new Error(extraction.error ?? "Could not extract document text.");
  return {
    name: file.name,
    relative_path: relativePath,
    extension: extensionForName(file.name),
    file_type: extraction.file_type,
    size_bytes: file.size,
    chars_read: extraction.chars,
    page_count: extraction.page_count,
    extraction_warnings: extraction.warnings,
    text_excerpt_or_text: extraction.text,
  };
}

export async function extractTextFromBrowserFile(file: File, maxCharsPerFile: number): Promise<DocumentTextExtractionResult> {
  const extension = extensionForName(file.name);
  if (extension === ".pdf") {
    const { extractPdfText } = await import("./documentExtractors/pdfExtractor");
    return extractPdfText(file, { maxCharsPerFile });
  }
  if (extension === ".docx") {
    const { extractDocxText } = await import("./documentExtractors/docxExtractor");
    return extractDocxText(file, { maxCharsPerFile });
  }
  const warnings: string[] = [];
  const text = await file.text();
  const truncated = truncateExtractedText(text, maxCharsPerFile, warnings);
  return {
    ok: true,
    text: truncated.text,
    chars: truncated.chars,
    file_type: "text",
    warnings,
  };
}

export async function readDocumentsForSummary(
  rootHandle: FileSystemDirectoryHandle,
  scanResult: BrowserFolderScanResult,
  options: DocumentReadOptions = {},
): Promise<BrowserDocumentReadResult> {
  const maxFilesToRead = options.maxFilesToRead ?? 20;
  const maxFileSizeMb = options.maxFileSizeMb ?? 3;
  const maxTotalChars = options.maxTotalChars ?? 120000;
  const maxCharsPerFile = options.maxCharsPerFile ?? 30000;
  const selection = options.selectedFiles;
  const { candidates: scannedCandidates, skipped } = getReadableFilesFromScan(scanResult, options.instruction ?? "");
  const selectedPaths = selection ? new Set(selection.map((file) => normalizeRelative(file.relative_path))) : null;
  const candidates = selectedPaths
    ? scannedCandidates.filter((file) => selectedPaths.has(normalizeRelative(file.relative_path)))
    : scannedCandidates;
  const files_read: ReadDocumentFile[] = [];
  const warnings: string[] = [];
  let total_chars = 0;

  for (const file of candidates.slice(0, maxFilesToRead)) {
    if (total_chars >= maxTotalChars) {
      skipped.push({ relative_path: file.relative_path, reason: `Total text limit of ${maxTotalChars.toLocaleString()} characters reached.` });
      continue;
    }
    if (file.size_bytes > maxFileSizeMb * 1024 * 1024) {
      skipped.push({ relative_path: file.relative_path, reason: `File is larger than ${maxFileSizeMb} MB.` });
      continue;
    }
    try {
      options.onProgress?.(progressMessageForExtension(file.extension));
      const readFile = await readTextFileFromHandle(rootHandle, file.relative_path, { maxFileSizeMb, maxCharsPerFile });
      if (total_chars + readFile.chars_read > maxTotalChars) {
        const remaining = Math.max(0, maxTotalChars - total_chars);
        readFile.text_excerpt_or_text = readFile.text_excerpt_or_text.slice(0, remaining);
        readFile.chars_read = readFile.text_excerpt_or_text.length;
        warnings.push(`Summary used first ${maxTotalChars.toLocaleString()} characters due to size limit.`);
      }
      if (file.extension.toLowerCase() === ".pdf" && readFile.page_count) {
        warnings.push(`${file.relative_path}: extracted selectable text from ${readFile.page_count} PDF pages.`);
      }
      warnings.push(...readFile.extraction_warnings.map((warning) => `${file.relative_path}: ${warning}`));
      total_chars += readFile.chars_read;
      files_read.push(readFile);
    } catch (error) {
      skipped.push({ relative_path: file.relative_path, reason: error instanceof Error ? error.message : String(error) });
    }
  }

  if (candidates.length > maxFilesToRead) {
    skipped.push(...candidates.slice(maxFilesToRead).map((file) => ({ relative_path: file.relative_path, reason: `Limited to first ${maxFilesToRead} readable files.` })));
  }

  return { files_read, skipped, total_chars, warnings };
}

function requestedExtensionsFromInstruction(instruction: string): string[] {
  const text = instruction.toLowerCase();
  const extensions: string[] = [];
  if (/\b(pdf|pdfs)\b/.test(text)) extensions.push(".pdf");
  if (/\b(docx|word)\b/.test(text)) extensions.push(".docx");
  if (/\b(markdown|md)\b/.test(text)) extensions.push(".md");
  if (/\b(txt|text)\b/.test(text)) extensions.push(".txt");
  if (/\b(log|logs)\b/.test(text)) extensions.push(".log");
  if (/\b(json)\b/.test(text)) extensions.push(".json");
  if (/\b(csv)\b/.test(text)) extensions.push(".csv");
  return extensions;
}

function progressMessageForExtension(extension: string): string {
  const normalized = extension.toLowerCase();
  if (normalized === ".pdf") return "Reading PDF pages...";
  if (normalized === ".docx") return "Reading DOCX documents...";
  return "Extracting text from selected files...";
}

function isBlockedPath(relativePath: string): boolean {
  return relativePath.split("/").some((segment) => BLOCKED_SEGMENTS.has(segment));
}

function normalizeRelative(path: string): string {
  return path.replace(/\\/g, "/");
}

function extensionForName(name: string): string {
  const index = name.lastIndexOf(".");
  if (index <= 0) return "";
  return name.slice(index).toLowerCase();
}
