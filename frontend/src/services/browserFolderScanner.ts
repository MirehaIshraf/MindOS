import type { FileSnapshotItem, FileSnapshotResponse } from "../types";

type DirectoryHandleWithValues = FileSystemDirectoryHandle & {
  values: () => AsyncIterable<FileSystemDirectoryHandle | FileSystemFileHandle>;
};

export type BrowserFolderScanOptions = {
  maxDepth?: number;
  maxFiles?: number;
  includeHidden?: boolean;
};

export type BrowserFolderScanResult = FileSnapshotResponse & {
  source: "browser_handle";
  root_path: null;
  root_name: string;
  display_name: string;
};

export async function scanBrowserFolder(
  handle: FileSystemDirectoryHandle,
  options: BrowserFolderScanOptions = {},
): Promise<BrowserFolderScanResult> {
  const maxDepth = clamp(options.maxDepth ?? 2, 0, 5);
  const maxFiles = clamp(options.maxFiles ?? 500, 1, 1000);
  const includeHidden = options.includeHidden ?? false;
  const files: FileSnapshotItem[] = [];
  const folders: FileSnapshotItem[] = [];
  const warnings: string[] = [];
  const state = { truncated: false, depthWarning: false };

  function addWarning(message: string) {
    if (!warnings.includes(message)) warnings.push(message);
  }

  async function walk(directory: FileSystemDirectoryHandle, relativeRoot: string, depth: number) {
    if (files.length >= maxFiles) {
      state.truncated = true;
      addWarning(`Scan was limited to ${maxFiles} files.`);
      return;
    }
    if (depth > maxDepth) {
      state.truncated = true;
      if (!state.depthWarning) {
        addWarning(`Depth limit reached at ${maxDepth}; deeper folders skipped.`);
        state.depthWarning = true;
      }
      return;
    }

    try {
      for await (const entry of (directory as DirectoryHandleWithValues).values()) {
        if (files.length >= maxFiles) {
          state.truncated = true;
          addWarning(`Scan was limited to ${maxFiles} files.`);
          return;
        }
        if (!includeHidden && entry.name.startsWith(".")) continue;

        const relativePath = joinRelative(relativeRoot, entry.name);
        try {
          if (entry.kind === "directory") {
            folders.push(toFolderItem(entry.name, relativePath));
            await walk(entry, relativePath, depth + 1);
          } else {
            const file = await entry.getFile();
            files.push(toFileItem(file, relativePath));
          }
        } catch (error) {
          addWarning(`Could not inspect ${relativePath}: ${getErrorText(error)}`);
        }
      }
    } catch (error) {
      addWarning(`Could not read ${relativeRoot || directory.name}: ${getErrorText(error)}`);
    }
  }

  await walk(handle, "", 0);

  return {
    source: "browser_handle",
    root_path: null,
    root_name: handle.name,
    display_name: handle.name,
    files,
    folders,
    total_files: files.length,
    total_folders: folders.length,
    total_size_bytes: files.reduce((total, file) => total + file.size_bytes, 0),
    max_depth: maxDepth,
    max_files: maxFiles,
    truncated: state.truncated,
    warnings,
  };
}

function toFileItem(file: File, relativePath: string): FileSnapshotItem {
  return {
    name: file.name,
    path: relativePath,
    relative_path: relativePath,
    extension: extensionForName(file.name),
    size_bytes: file.size,
    modified_at: new Date(file.lastModified).toISOString(),
    is_dir: false,
    is_hidden: file.name.startsWith("."),
  };
}

function toFolderItem(name: string, relativePath: string): FileSnapshotItem {
  return {
    name,
    path: relativePath,
    relative_path: relativePath,
    extension: "",
    size_bytes: 0,
    modified_at: new Date(0).toISOString(),
    is_dir: true,
    is_hidden: name.startsWith("."),
  };
}

function joinRelative(root: string, name: string): string {
  return root ? `${root}/${name}` : name;
}

function extensionForName(name: string): string {
  const index = name.lastIndexOf(".");
  if (index <= 0) return "";
  return name.slice(index).toLowerCase();
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function getErrorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
