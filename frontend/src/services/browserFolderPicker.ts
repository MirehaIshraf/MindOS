type BrowserDirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options?: { mode?: "read" | "readwrite" }) => Promise<FileSystemDirectoryHandle>;
};

export type BrowserPickedFolder = {
  kind: "browser_handle";
  name: string;
  handle: FileSystemDirectoryHandle;
};

export function isBrowserFolderPickerSupported(): boolean {
  return typeof (window as BrowserDirectoryPickerWindow).showDirectoryPicker === "function";
}

export async function chooseBrowserFolder(): Promise<BrowserPickedFolder | null> {
  const picker = (window as BrowserDirectoryPickerWindow).showDirectoryPicker;
  if (!picker) return null;

  try {
    const handle = await picker({ mode: "readwrite" });
    return { kind: "browser_handle", name: handle.name, handle };
  } catch (error) {
    if (isAbortError(error)) return null;
    try {
      const handle = await picker({ mode: "read" });
      return { kind: "browser_handle", name: handle.name, handle };
    } catch (readError) {
      if (isAbortError(readError)) return null;
      throw readError;
    }
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
