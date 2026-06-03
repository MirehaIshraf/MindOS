import type { FileOperation, FileTaskPlan } from "../types";

type DirectoryHandleWithRemove = FileSystemDirectoryHandle & {
  removeEntry: (name: string, options?: { recursive?: boolean }) => Promise<void>;
};

type WritableFileHandle = FileSystemFileHandle & {
  createWritable: () => Promise<FileSystemWritableFileStream>;
};

type PermissionMode = "read" | "readwrite";

type PermissionHandle = FileSystemDirectoryHandle & {
  queryPermission?: (descriptor?: { mode?: PermissionMode }) => Promise<PermissionState>;
  requestPermission?: (descriptor?: { mode?: PermissionMode }) => Promise<PermissionState>;
};

export type BrowserExecutionProgress = {
  step: "preparing" | "creating_folders" | "moving_files" | "finalizing" | "completed" | "failed";
  message: string;
  createdFolders: number;
  totalFolders: number;
  movedFiles: number;
  totalMoves: number;
  errors: string[];
  percent: number;
};

export type BrowserUndoOperation = {
  type: "move_file" | "remove_created_folder_if_empty";
  from_relative_path?: string;
  to_relative_path?: string;
  relative_path?: string;
  reason: string;
};

export type BrowserExecutionResult = {
  status: "completed" | "partial" | "failed";
  createdFolders: number;
  movedFiles: number;
  skipped: string[];
  errors: string[];
  undoOperations: BrowserUndoOperation[];
  undoAvailable: boolean;
};

export type BrowserUndoResult = {
  status: "undone" | "partial" | "failed";
  undoneOperations: number;
  errors: string[];
};

export async function executeBrowserFilePlan(
  rootHandle: FileSystemDirectoryHandle,
  plan: FileTaskPlan,
  callbacks: { onProgress?: (progress: BrowserExecutionProgress) => void } = {},
): Promise<BrowserExecutionResult> {
  const folders = plan.folders_to_create.filter((operation) => operation.type === "create_folder");
  const moves = plan.files_to_move.filter((operation) => operation.type === "move_file");
  const totalSteps = Math.max(1, folders.length + moves.length + 2);
  const errors: string[] = [];
  const skipped: string[] = [];
  const undoOperations: BrowserUndoOperation[] = [];
  let createdFolders = 0;
  let movedFiles = 0;

  const emit = (progress: Omit<BrowserExecutionProgress, "createdFolders" | "totalFolders" | "movedFiles" | "totalMoves" | "errors">) => {
    callbacks.onProgress?.({
      ...progress,
      createdFolders,
      totalFolders: folders.length,
      movedFiles,
      totalMoves: moves.length,
      errors: [...errors],
    });
  };

  emit({ step: "preparing", message: "Preparing execution...", percent: 5 });
  const permission = await ensureReadWritePermission(rootHandle);
  if (!permission) {
    return {
      status: "failed",
      createdFolders: 0,
      movedFiles: 0,
      skipped,
      errors: ["MindOS needs folder write permission to organize files."],
      undoOperations: [],
      undoAvailable: false,
    };
  }

  emit({ step: "creating_folders", message: "Creating folders...", percent: 10 });
  for (const operation of folders) {
    const folderPath = operation.relative_to || operation.path || "";
    try {
      await createFolder(rootHandle, folderPath);
      createdFolders += 1;
      undoOperations.push({
        type: "remove_created_folder_if_empty",
        relative_path: normalizeRelativePath(folderPath),
        reason: "Remove created folder if empty.",
      });
    } catch (error) {
      errors.push(`${folderPath}: ${getErrorText(error)}`);
    }
    emit({
      step: "creating_folders",
      message: "Creating folders...",
      percent: progressPercent(createdFolders, folders.length + moves.length, totalSteps),
    });
  }

  emit({ step: "moving_files", message: "Moving files...", percent: progressPercent(createdFolders, folders.length + moves.length, totalSteps) });
  for (const operation of moves) {
    const fromPath = operation.relative_from || operation.from_path || "";
    const toPath = operation.relative_to || operation.to_path || "";
    try {
      await moveFileWithinRoot(rootHandle, fromPath, toPath);
      movedFiles += 1;
      undoOperations.push({
        type: "move_file",
        from_relative_path: normalizeRelativePath(toPath),
        to_relative_path: normalizeRelativePath(fromPath),
        reason: "Move file back to original location.",
      });
    } catch (error) {
      const message = `${fromPath}: ${getErrorText(error)}`;
      errors.push(message);
      skipped.push(message);
    }
    emit({
      step: "moving_files",
      message: "Moving files...",
      percent: progressPercent(createdFolders + movedFiles, folders.length + moves.length, totalSteps),
    });
  }

  emit({ step: "finalizing", message: "Finalizing result...", percent: 95 });
  const status = errors.length === 0 ? "completed" : createdFolders > 0 || movedFiles > 0 ? "partial" : "failed";
  emit({ step: status === "failed" ? "failed" : "completed", message: status === "failed" ? "Execution failed." : "Execution complete.", percent: 100 });

  return {
    status,
    createdFolders,
    movedFiles,
    skipped,
    errors,
    undoOperations,
    undoAvailable: undoOperations.length > 0,
  };
}

export async function undoBrowserFilePlan(
  rootHandle: FileSystemDirectoryHandle,
  undoOperations: BrowserUndoOperation[],
): Promise<BrowserUndoResult> {
  const errors: string[] = [];
  let undoneOperations = 0;
  const permission = await ensureReadWritePermission(rootHandle);
  if (!permission) {
    return {
      status: "failed",
      undoneOperations: 0,
      errors: ["MindOS needs folder write permission to undo file moves."],
    };
  }

  for (const operation of [...undoOperations].reverse()) {
    try {
      if (operation.type === "move_file" && operation.from_relative_path && operation.to_relative_path) {
        await moveFileWithinRoot(rootHandle, operation.from_relative_path, operation.to_relative_path);
        undoneOperations += 1;
      } else if (operation.type === "remove_created_folder_if_empty" && operation.relative_path) {
        await removeFolderIfEmpty(rootHandle, operation.relative_path);
        undoneOperations += 1;
      }
    } catch (error) {
      errors.push(`${operation.type}: ${getErrorText(error)}`);
    }
  }

  return {
    status: errors.length === 0 ? "undone" : undoneOperations > 0 ? "partial" : "failed",
    undoneOperations,
    errors,
  };
}

export async function createFolder(rootHandle: FileSystemDirectoryHandle, folderName: string): Promise<FileSystemDirectoryHandle> {
  return getDirectoryByRelativePath(rootHandle, folderName, true);
}

export async function moveFileWithinRoot(
  rootHandle: FileSystemDirectoryHandle,
  fromRelativePath: string,
  toRelativePath: string,
): Promise<void> {
  const fromPath = normalizeRelativePath(fromRelativePath);
  const toPath = normalizeRelativePath(toRelativePath);
  if (!fromPath || !toPath) throw new Error("Move operation requires source and destination paths.");
  if (fromPath === toPath) throw new Error("Source and destination are the same.");

  const sourceParent = await getDirectoryByRelativePath(rootHandle, parentPath(fromPath), false);
  const destinationParent = await getDirectoryByRelativePath(rootHandle, parentPath(toPath), true);
  const sourceName = basename(fromPath);
  const destinationName = basename(toPath);
  const sourceHandle = await sourceParent.getFileHandle(sourceName, { create: false });

  if (await fileExists(destinationParent, destinationName)) {
    throw new Error("Destination already exists. No overwrite allowed.");
  }

  const file = await sourceHandle.getFile();
  const destinationHandle = await destinationParent.getFileHandle(destinationName, { create: true });
  const writable = await (destinationHandle as WritableFileHandle).createWritable();
  try {
    await writable.write(file);
  } finally {
    await writable.close();
  }

  const writtenFile = await destinationHandle.getFile();
  if (writtenFile.size !== file.size) {
    throw new Error("Destination verification failed after write.");
  }

  await (sourceParent as DirectoryHandleWithRemove).removeEntry(sourceName);
}

export async function getDirectoryByRelativePath(
  rootHandle: FileSystemDirectoryHandle,
  relativeDirPath: string,
  create = false,
): Promise<FileSystemDirectoryHandle> {
  const normalized = normalizeRelativePath(relativeDirPath);
  if (!normalized) return rootHandle;

  let current = rootHandle;
  for (const segment of pathSegments(normalized)) {
    current = await current.getDirectoryHandle(segment, { create });
  }
  return current;
}

export async function getFileHandleByRelativePath(
  rootHandle: FileSystemDirectoryHandle,
  relativeFilePath: string,
): Promise<FileSystemFileHandle> {
  const normalized = normalizeRelativePath(relativeFilePath);
  if (!normalized) throw new Error("File path is required.");
  const directory = await getDirectoryByRelativePath(rootHandle, parentPath(normalized), false);
  return directory.getFileHandle(basename(normalized), { create: false });
}

async function removeFolderIfEmpty(rootHandle: FileSystemDirectoryHandle, relativePath: string): Promise<void> {
  const normalized = normalizeRelativePath(relativePath);
  if (!normalized) return;
  const parent = await getDirectoryByRelativePath(rootHandle, parentPath(normalized), false);
  await (parent as DirectoryHandleWithRemove).removeEntry(basename(normalized), { recursive: false });
}

async function ensureReadWritePermission(handle: FileSystemDirectoryHandle): Promise<boolean> {
  const permissionHandle = handle as PermissionHandle;
  if (!permissionHandle.queryPermission || !permissionHandle.requestPermission) return true;
  const current = await permissionHandle.queryPermission({ mode: "readwrite" });
  if (current === "granted") return true;
  const requested = await permissionHandle.requestPermission({ mode: "readwrite" });
  return requested === "granted";
}

async function fileExists(directory: FileSystemDirectoryHandle, name: string): Promise<boolean> {
  try {
    await directory.getFileHandle(name, { create: false });
    return true;
  } catch (error) {
    if (error instanceof DOMException && error.name === "NotFoundError") return false;
    throw error;
  }
}

function normalizeRelativePath(path: string): string {
  const normalized = path.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
  if (!normalized) return "";
  const segments = pathSegments(normalized);
  return segments.join("/");
}

function pathSegments(path: string): string[] {
  const segments = path.split("/").filter(Boolean);
  if (segments.some((segment) => segment === "." || segment === ".." || segment.includes("\0"))) {
    throw new Error("Unsafe relative path.");
  }
  return segments;
}

function parentPath(path: string): string {
  const segments = pathSegments(path);
  return segments.slice(0, -1).join("/");
}

function basename(path: string): string {
  const segments = pathSegments(path);
  const name = segments[segments.length - 1];
  if (!name) throw new Error("Path name is required.");
  return name;
}

function progressPercent(doneOperations: number, operationCount: number, totalSteps: number): number {
  if (operationCount <= 0) return 90;
  return Math.min(90, Math.max(10, Math.round(((doneOperations + 1) / totalSteps) * 90)));
}

function getErrorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
