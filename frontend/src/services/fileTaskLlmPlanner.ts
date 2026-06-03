import { planFileTaskWithLlm } from "./api";
import type { FileOperation, FileTaskPlan } from "../types";
import type { BrowserFolderScanResult } from "./browserFolderScanner";

export type FileTaskIntent =
  | { intent: "document_summary"; supported: true; label: "Summarize documents" }
  | { intent: "organize_by_type"; supported: true; label: "Organize folder" }
  | { intent: "move_category"; supported: true; label: "Move category"; targetCategory: string; requestedFolderName: string }
  | { intent: "create_folders"; supported: true; label: "Create folders"; folderNames: string[] }
  | { intent: "rename_files"; supported: false; label: "Rename files"; reason: string }
  | { intent: "unknown_or_unsupported"; supported: false; label: "Unsupported"; reason: string };

const CATEGORY_EXTENSIONS: Record<string, string[]> = {
  PDFs: [".pdf"],
  Images: [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"],
  Videos: [".mp4", ".mov", ".avi", ".mkv", ".webm"],
  Audio: [".mp3", ".wav", ".m4a", ".flac", ".aac"],
  Archives: [".zip", ".rar", ".7z", ".tar", ".gz"],
  Installers: [".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm"],
  Code: [".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".xml", ".yml", ".yaml"],
  Documents: [".doc", ".docx", ".txt", ".md", ".rtf"],
  Spreadsheets: [".xls", ".xlsx", ".csv"],
  Presentations: [".ppt", ".pptx"],
};

const CATEGORY_ALIASES: Array<{ category: string; terms: string[] }> = [
  { category: "Installers", terms: ["installer", "installers", "setup", "setups", "exe", "msi", "dmg"] },
  { category: "PDFs", terms: ["pdf", "pdfs"] },
  { category: "Images", terms: ["image", "images", "photo", "photos", "picture", "pictures", "screenshot", "screenshots"] },
  { category: "Videos", terms: ["video", "videos"] },
  { category: "Audio", terms: ["audio", "music", "sound"] },
  { category: "Archives", terms: ["archive", "archives", "zip", "zips", "compressed"] },
  { category: "Documents", terms: ["document", "documents", "docs", "office files", "office"] },
  { category: "Code", terms: ["code", "developer", "source"] },
  { category: "Spreadsheets", terms: ["spreadsheet", "spreadsheets", "excel", "csv"] },
  { category: "Presentations", terms: ["presentation", "presentations", "slides", "powerpoint"] },
];

export function classifyFileTaskIntent(instruction: string): FileTaskIntent {
  const text = instruction.trim().toLowerCase();
  if (/\b(summarize|summary|notes|report|read docs|read documents|read these documents|make notes)\b/.test(text)) {
    if (/\b(delete|rewrite|edit|upload|email|overwrite)\b/.test(text)) {
      return { intent: "unknown_or_unsupported", supported: false, label: "Unsupported", reason: "This document task is not supported safely yet." };
    }
    return { intent: "document_summary", supported: true, label: "Summarize documents" };
  }
  if (!text || /\b(organize|sort|clean)\b/.test(text) && /\b(type|folder|downloads?)\b/.test(text)) {
    return { intent: "organize_by_type", supported: true, label: "Organize folder" };
  }
  if (/\b(delete|remove|compress|zip this|upload|email|run|execute|shell|script|overwrite|replace)\b/.test(text)) {
    return { intent: "unknown_or_unsupported", supported: false, label: "Unsupported", reason: "This file task is not supported safely yet." };
  }
  if (/\b(rename|renaming)\b/.test(text)) {
    return { intent: "rename_files", supported: false, label: "Rename files", reason: "Renaming files is not connected in this MVP." };
  }
  const category = detectCategory(text);
  if (category && /\b(move|put|group|place)\b/.test(text)) {
    return { intent: "move_category", supported: true, label: "Move category", targetCategory: category, requestedFolderName: category };
  }
  if (/\b(create|make)\b/.test(text) && /\bfolders?\b/.test(text)) {
    const folderNames = extractRequestedFolderNames(instruction);
    return { intent: "create_folders", supported: true, label: "Create folders", folderNames };
  }
  if (/\b(organize|sort|clean)\b/.test(text)) {
    return { intent: "organize_by_type", supported: true, label: "Organize folder" };
  }
  return { intent: "unknown_or_unsupported", supported: false, label: "Unsupported", reason: "MindOS could not identify a safe file task from that request." };
}

export function shouldUseLlmFilePlanning(instruction: string, intent = classifyFileTaskIntent(instruction)): boolean {
  if (!intent.supported) return false;
  if (intent.intent === "move_category" && /\b(ai|research|related|named|mindos|model|dataset|paper|office|study)\b/i.test(instruction)) return true;
  if (intent.intent === "document_summary" || intent.intent === "organize_by_type" || intent.intent === "move_category" || intent.intent === "create_folders") return false;
  return true;
}

export async function createLlmAssistedBrowserFilePlan(scan: BrowserFolderScanResult, instruction: string): Promise<FileTaskPlan> {
  const intent = classifyFileTaskIntent(instruction);
  const plan = await planFileTaskWithLlm({
    instruction,
    root_name: scan.display_name || scan.root_name || "Selected folder",
    files: scan.files.map((file) => ({
      name: file.name,
      relative_path: file.relative_path,
      extension: file.extension,
      size_bytes: file.size_bytes,
      modified_at: file.modified_at,
      category: categoryForExtension(file.extension),
      is_hidden: file.is_hidden,
    })),
    folders: scan.folders.map((folder) => ({
      name: folder.name,
      relative_path: folder.relative_path,
      is_hidden: folder.is_hidden,
    })),
    allowed_operations: ["create_folder", "move_file"],
    max_operations: 500,
  });
  return validateBrowserFilePlan(plan, scan, intent);
}

export function buildExactIntentFallbackPlan(
  scan: BrowserFolderScanResult,
  instruction: string,
  warning?: string,
): FileTaskPlan {
  const intent = classifyFileTaskIntent(instruction);
  if (!intent.supported) return unsupportedPlan(scan, instruction, intent.reason, warning);
  if (intent.intent === "document_summary") return unsupportedPlan(scan, instruction, "Use the document summary preview flow for this request.", warning);
  if (intent.intent === "move_category") return moveCategoryPlan(scan, instruction, intent, warning);
  if (intent.intent === "create_folders") return createFoldersPlan(scan, instruction, intent, warning);
  return organizeByTypePlan(scan, instruction, warning);
}

export function validateBrowserFilePlan(plan: FileTaskPlan, scan: BrowserFolderScanResult, intent = classifyFileTaskIntent(plan.instruction)): FileTaskPlan {
  const existingFiles = new Set(scan.files.map((file) => normalizeRelative(file.relative_path)));
  const existingFolders = new Set(scan.folders.map((folder) => normalizeRelative(folder.relative_path)));
  const plannedDestinations = new Set<string>();
  const blockedReasons = [...plan.blocked_reasons];
  const skipped = [...plan.skipped];
  const safeOperations: FileOperation[] = [];

  if (!intent.supported) {
    return unsupportedPlan(scan, plan.instruction, intent.reason, plan.planner_warning ?? undefined);
  }

  for (const operation of plan.operations) {
    if (operation.type !== "create_folder" && operation.type !== "move_file") {
      blockedReasons.push(`Blocked ${operation.type}: only create_folder and move_file are allowed.`);
      continue;
    }
    if (operation.type === "create_folder") {
      const folderPath = normalizeRelative(operation.relative_to || operation.path || "");
      if (!isSafeRelativePath(folderPath)) {
        blockedReasons.push("Blocked unsafe folder path.");
        continue;
      }
      if (intent.intent === "move_category" && folderPath !== intent.requestedFolderName) {
        skipped.push({ path: folderPath, relative_path: folderPath, reason: "Folder was outside the requested category task." });
        continue;
      }
      if (existingFiles.has(folderPath)) {
        skipped.push({ path: folderPath, relative_path: folderPath, reason: "Destination exists as a file." });
        continue;
      }
      if (existingFolders.has(folderPath)) continue;
      safeOperations.push({ ...operation, type: "create_folder", tool: "file.create_folder", path: null, from_path: null, to_path: null, relative_from: null, relative_to: folderPath, status: "planned" });
      existingFolders.add(folderPath);
      continue;
    }

    const fromPath = normalizeRelative(operation.relative_from || operation.from_path || "");
    const toPath = normalizeRelative(operation.relative_to || operation.to_path || "");
    const source = scan.files.find((file) => normalizeRelative(file.relative_path) === fromPath);
    if (!isSafeRelativePath(fromPath) || !isSafeRelativePath(toPath)) {
      blockedReasons.push("Blocked unsafe move path.");
      continue;
    }
    if (!source) {
      skipped.push({ path: fromPath, relative_path: fromPath, reason: "Source file was not in the scan." });
      continue;
    }
    if (intent.intent === "move_category" && categoryForExtension(source.extension) !== intent.targetCategory) {
      skipped.push({ path: fromPath, relative_path: fromPath, reason: `Not a ${intent.targetCategory} file.` });
      continue;
    }
    if (intent.intent === "move_category" && parentPath(toPath) !== intent.requestedFolderName) {
      skipped.push({ path: fromPath, relative_path: fromPath, reason: "Destination was outside the requested category folder." });
      continue;
    }
    if (existingFiles.has(toPath) || plannedDestinations.has(toPath)) {
      skipped.push({ path: fromPath, relative_path: fromPath, reason: "Destination already exists. No overwrite allowed." });
      continue;
    }
    if (!toPath.includes("/")) {
      skipped.push({ path: fromPath, relative_path: fromPath, reason: "Destination folder was not specified." });
      continue;
    }
    safeOperations.push({ ...operation, type: "move_file", tool: "file.move_file", from_path: null, to_path: null, path: null, relative_from: fromPath, relative_to: toPath, status: "planned" });
    plannedDestinations.add(toPath);
  }

  const operations = assignOperationIds(dedupeCreateFolders(safeOperations));
  const foldersToCreate = operations.filter((operation) => operation.type === "create_folder");
  const filesToMove = operations.filter((operation) => operation.type === "move_file");
  const status = blockedReasons.length && operations.length === 0 ? "blocked" : operations.length ? "awaiting_confirmation" : "empty";

  return {
    ...plan,
    operations,
    folders_to_create: foldersToCreate,
    files_to_move: filesToMove,
    skipped: dedupeSkipped(skipped),
    blocked_reasons: dedupe(blockedReasons),
    total_operations: operations.length,
    create_folder_count: foldersToCreate.length,
    move_file_count: filesToMove.length,
    copy_file_count: 0,
    rename_file_count: 0,
    status,
    preview_only: true,
  };
}

function moveCategoryPlan(scan: BrowserFolderScanResult, instruction: string, intent: Extract<FileTaskIntent, { intent: "move_category" }>, warning?: string): FileTaskPlan {
  const existingFolders = new Set(scan.folders.map((folder) => normalizeRelative(folder.relative_path)));
  const existingFiles = new Set(scan.files.map((file) => normalizeRelative(file.relative_path)));
  const matchedFiles = scan.files.filter((file) => categoryForExtension(file.extension) === intent.targetCategory && !file.is_hidden);
  const skipped = scan.files
    .filter((file) => categoryForExtension(file.extension) !== intent.targetCategory)
    .map((file) => ({ path: file.path, relative_path: file.relative_path, reason: `Not a ${intent.targetCategory} file.` }));

  if (!matchedFiles.length) {
    return basePlan(scan, instruction, {
      summary: `No ${singularCategory(intent.targetCategory).toLowerCase()} files were found in this folder.`,
      status: "empty",
      warnings: [`Scanned ${scan.total_files} files but found 0 ${singularCategory(intent.targetCategory).toLowerCase()} files.`],
      skipped,
      planner_warning: warning ?? null,
    });
  }

  const filesToMove: FileOperation[] = [];
  for (const file of matchedFiles) {
    const sourcePath = normalizeRelative(file.relative_path);
    const destinationPath = normalizeRelative(`${intent.requestedFolderName}/${file.name}`);
    if (sourcePath === destinationPath || parentPath(sourcePath) === intent.requestedFolderName) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Already in the requested folder." });
      continue;
    }
    if (existingFiles.has(destinationPath)) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Destination already exists. No overwrite allowed." });
      continue;
    }
    filesToMove.push({ id: "", type: "move_file", tool: "file.move_file", from_path: null, to_path: null, path: null, relative_from: sourcePath, relative_to: destinationPath, reason: `${singularCategory(intent.targetCategory)} file matches the requested category.`, status: "planned" });
  }
  const foldersToCreate: FileOperation[] = filesToMove.length && !existingFolders.has(intent.requestedFolderName)
    ? [{ id: "", type: "create_folder", tool: "file.create_folder", from_path: null, to_path: null, path: null, relative_from: null, relative_to: intent.requestedFolderName, reason: `Create ${intent.requestedFolderName} for matching files.`, status: "planned" }]
    : [];
  const operations = assignOperationIds([...foldersToCreate, ...filesToMove]);
  return basePlan(scan, instruction, {
    summary: filesToMove.length ? `Move ${filesToMove.length} ${singularCategory(intent.targetCategory).toLowerCase()} files into ${intent.requestedFolderName}.` : `No ${singularCategory(intent.targetCategory).toLowerCase()} files need to be moved.`,
    operations,
    folders_to_create: operations.filter((operation) => operation.type === "create_folder"),
    files_to_move: operations.filter((operation) => operation.type === "move_file"),
    skipped,
    status: operations.length ? "awaiting_confirmation" : "empty",
    planner_warning: warning ?? null,
  });
}

function createFoldersPlan(scan: BrowserFolderScanResult, instruction: string, intent: Extract<FileTaskIntent, { intent: "create_folders" }>, warning?: string): FileTaskPlan {
  const existingFolders = new Set(scan.folders.map((folder) => normalizeRelative(folder.relative_path)));
  const folderNames = intent.folderNames.length ? intent.folderNames : ["Documents", "Images", "Code"];
  const operations = assignOperationIds(folderNames.filter((name) => !existingFolders.has(name)).map((name) => ({ id: "", type: "create_folder" as const, tool: "file.create_folder", from_path: null, to_path: null, path: null, relative_from: null, relative_to: name, reason: "Folder requested by user.", status: "planned" as const })));
  return basePlan(scan, instruction, {
    summary: operations.length ? `Create ${operations.length} folders: ${operations.map((operation) => operation.relative_to).join(", ")}.` : "Requested folders already exist.",
    operations,
    folders_to_create: operations,
    status: operations.length ? "awaiting_confirmation" : "empty",
    planner_warning: warning ?? null,
  });
}

function organizeByTypePlan(scan: BrowserFolderScanResult, instruction: string, warning?: string): FileTaskPlan {
  const includeOther = shouldIncludeOther(instruction);
  const existingFolders = new Set(scan.folders.map((folder) => normalizeRelative(folder.relative_path)));
  const existingFiles = new Set(scan.files.map((file) => normalizeRelative(file.relative_path)));
  const skipped: FileTaskPlan["skipped"] = [];
  const destinationFolders = new Set<string>();
  const filesToMove: FileOperation[] = [];

  for (const file of scan.files) {
    const category = categoryForExtension(file.extension);
    if (category === "Other" && !includeOther) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Unknown file type." });
      continue;
    }
    const sourcePath = normalizeRelative(file.relative_path);
    const destinationPath = normalizeRelative(`${category}/${file.name}`);
    if (sourcePath === destinationPath || parentPath(sourcePath) === category) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Already organized." });
      continue;
    }
    if (existingFiles.has(destinationPath)) {
      skipped.push({ path: file.path, relative_path: file.relative_path, reason: "Destination already exists. No overwrite allowed." });
      continue;
    }
    destinationFolders.add(category);
    filesToMove.push({ id: "", type: "move_file", tool: "file.move_file", from_path: null, to_path: null, path: null, relative_from: sourcePath, relative_to: destinationPath, reason: `${singularCategory(category)} file should be grouped under ${category}.`, status: "planned" });
  }
  const foldersToCreate = [...destinationFolders].sort().filter((folder) => !existingFolders.has(folder)).map((folder) => ({ id: "", type: "create_folder" as const, tool: "file.create_folder", from_path: null, to_path: null, path: null, relative_from: null, relative_to: folder, reason: `Create ${folder} folder for organized files.`, status: "planned" as const }));
  const operations = assignOperationIds([...foldersToCreate, ...filesToMove]);
  const categories = [...new Set(filesToMove.map((operation) => parentPath(operation.relative_to || "")))].sort();
  return basePlan(scan, instruction, {
    summary: filesToMove.length ? `Organize ${filesToMove.length} files by type into ${categories.join(", ")}.` : "No file moves are needed for this folder.",
    operations,
    folders_to_create: operations.filter((operation) => operation.type === "create_folder"),
    files_to_move: operations.filter((operation) => operation.type === "move_file"),
    skipped,
    status: operations.length ? "awaiting_confirmation" : "empty",
    planner_warning: warning ?? null,
  });
}

function unsupportedPlan(scan: BrowserFolderScanResult, instruction: string, reason: string, warning?: string): FileTaskPlan {
  return basePlan(scan, instruction, {
    summary: "MindOS cannot safely perform this file task yet.",
    status: "unsupported",
    blocked_reasons: [reason],
    planner_warning: warning ?? null,
  });
}

function basePlan(scan: BrowserFolderScanResult, instruction: string, overrides: Partial<FileTaskPlan>): FileTaskPlan {
  const operations = overrides.operations ?? [];
  const foldersToCreate = overrides.folders_to_create ?? [];
  const filesToMove = overrides.files_to_move ?? [];
  return {
    task_id: `browser-preview-${Date.now()}`,
    task_type: "file_organize",
    root_path: scan.display_name || scan.root_name || "Selected folder",
    instruction,
    summary: overrides.summary ?? "No safe file task plan was prepared.",
    risk_level: overrides.risk_level ?? "low",
    requires_confirmation: true,
    operations,
    folders_to_create: foldersToCreate,
    files_to_move: filesToMove,
    skipped: overrides.skipped ?? [],
    warnings: overrides.warnings ?? scan.warnings,
    blocked_reasons: overrides.blocked_reasons ?? [],
    status: overrides.status ?? (operations.length ? "awaiting_confirmation" : "empty"),
    total_operations: operations.length,
    create_folder_count: foldersToCreate.length,
    move_file_count: filesToMove.length,
    copy_file_count: 0,
    rename_file_count: 0,
    category_counts: buildCategoryCounts(scan),
    preview_only: true,
    planner_model: overrides.planner_model ?? null,
    planner_provider: overrides.planner_provider ?? null,
    planner_warning: overrides.planner_warning ?? null,
  };
}

function detectCategory(text: string) {
  for (const entry of CATEGORY_ALIASES) {
    if (entry.terms.some((term) => new RegExp(`\\b${escapeRegex(term)}\\b`, "i").test(text))) return entry.category;
  }
  return null;
}

function extractRequestedFolderNames(instruction: string) {
  return Object.keys(CATEGORY_EXTENSIONS).filter((category) => new RegExp(`\\b${category.toLowerCase()}\\b`, "i").test(instruction));
}

function categoryForExtension(extension: string) {
  const normalized = extension.toLowerCase();
  for (const [category, extensions] of Object.entries(CATEGORY_EXTENSIONS)) {
    if (extensions.includes(normalized)) return category;
  }
  return "Other";
}

function buildCategoryCounts(scan: BrowserFolderScanResult) {
  const counts: Record<string, number> = {};
  for (const file of scan.files) {
    const category = categoryForExtension(file.extension);
    counts[category] = (counts[category] ?? 0) + 1;
  }
  return counts;
}

function singularCategory(category: string) {
  if (category === "PDFs") return "PDF";
  if (category === "Installers") return "installer";
  return category.endsWith("s") ? category.slice(0, -1) : category;
}

function normalizeRelative(path: string) {
  return path.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "").replace(/\/+/g, "/");
}

function parentPath(path: string) {
  const normalized = normalizeRelative(path);
  const index = normalized.lastIndexOf("/");
  return index === -1 ? "" : normalized.slice(0, index);
}

function isSafeRelativePath(path: string) {
  if (!path || path.startsWith("/") || /^[a-zA-Z]:/.test(path)) return false;
  return path.split("/").every((segment) => segment && segment !== "." && segment !== ".." && !segment.includes("\0"));
}

function shouldIncludeOther(instruction: string) {
  const text = instruction.toLowerCase();
  return text.includes("unknown") || text.includes("others") || text.includes("other files");
}

function assignOperationIds(operations: FileOperation[]) {
  return operations.map((operation, index) => ({ ...operation, id: `op_${String(index + 1).padStart(3, "0")}` }));
}

function dedupeCreateFolders(operations: FileOperation[]) {
  const seen = new Set<string>();
  return operations.filter((operation) => {
    if (operation.type !== "create_folder") return true;
    const folder = operation.relative_to || "";
    if (seen.has(folder)) return false;
    seen.add(folder);
    return true;
  });
}

function dedupe(values: string[]) {
  return [...new Set(values)];
}

function dedupeSkipped(items: FileTaskPlan["skipped"]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.relative_path || item.path}:${item.reason}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
