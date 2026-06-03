type WritableFileHandle = FileSystemFileHandle & {
  createWritable: () => Promise<FileSystemWritableFileStream>;
};

export async function writeSummaryFile(
  rootHandle: FileSystemDirectoryHandle,
  filename: string,
  content: string,
): Promise<{ filename: string }> {
  const safeName = sanitizeFilename(filename);
  const finalName = await uniqueFilename(rootHandle, safeName);
  const fileHandle = await rootHandle.getFileHandle(finalName, { create: true });
  const writable = await (fileHandle as WritableFileHandle).createWritable();
  try {
    await writable.write(content);
  } finally {
    await writable.close();
  }
  return { filename: finalName };
}

async function uniqueFilename(rootHandle: FileSystemDirectoryHandle, filename: string): Promise<string> {
  const { base, extension } = splitFilename(filename);
  let candidate = `${base}${extension}`;
  let index = 1;
  while (await fileExists(rootHandle, candidate)) {
    candidate = `${base}-${index}${extension}`;
    index += 1;
  }
  return candidate;
}

async function fileExists(rootHandle: FileSystemDirectoryHandle, filename: string): Promise<boolean> {
  try {
    await rootHandle.getFileHandle(filename, { create: false });
    return true;
  } catch (error) {
    if (error instanceof DOMException && error.name === "NotFoundError") return false;
    throw error;
  }
}

function sanitizeFilename(filename: string): string {
  const trimmed = filename.trim() || "mindos-summary.md";
  const extension = trimmed.toLowerCase().endsWith(".txt") ? ".txt" : ".md";
  const stem = trimmed.replace(/\.(md|txt)$/i, "");
  const safeStem = stem
    .toLowerCase()
    .replace(/[\\/:*?"<>|#%&{}$!'@+`=\0]+/g, " ")
    .replace(/[_\s]+/g, "-")
    .replace(/[^a-z0-9-]+/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60)
    .replace(/-$/g, "");
  return `${safeStem || "mindos-summary"}${extension}`;
}

function splitFilename(filename: string): { base: string; extension: string } {
  const index = filename.lastIndexOf(".");
  if (index <= 0) return { base: filename, extension: ".md" };
  return { base: filename.slice(0, index), extension: filename.slice(index) };
}
