import { prepareDocumentSummary } from "./api";
import type { BrowserDocumentReadResult } from "./browserDocumentReader";
import type { DocumentSummaryPrepareResponse, DocumentSummaryStyle } from "../types";

export async function prepareBrowserDocumentSummary(
  instruction: string,
  folderName: string,
  readResult: BrowserDocumentReadResult,
  options: {
    outputFormat?: "markdown" | "text";
    outputFilename?: string;
    summaryStyle?: DocumentSummaryStyle;
  } = {},
): Promise<DocumentSummaryPrepareResponse> {
  const response = await prepareDocumentSummary({
    instruction,
    folder_name: folderName,
    files: readResult.files_read.map((file) => ({
      relative_path: file.relative_path,
      extension: file.extension,
      text: `File: ${file.relative_path}\nType: ${labelForExtension(file.extension)}\nExtracted text:\n${file.text_excerpt_or_text}`,
    })),
    files_skipped: readResult.skipped,
    output_format: options.outputFormat ?? "markdown",
    output_filename: options.outputFilename,
    summary_style: options.summaryStyle ?? "detailed",
  });

  return {
    ...response,
    warnings: [...readResult.warnings, ...response.warnings],
    files_skipped: response.files_skipped.length ? response.files_skipped : readResult.skipped,
  };
}

function labelForExtension(extension: string): string {
  const normalized = extension.toLowerCase();
  if (normalized === ".pdf") return "PDF";
  if (normalized === ".docx") return "DOCX";
  if (normalized === ".md") return "Markdown";
  if (normalized === ".txt") return "Text";
  if (normalized === ".log") return "Log";
  if (normalized === ".json") return "JSON";
  if (normalized === ".csv") return "CSV";
  return normalized.replace(/^\./, "").toUpperCase() || "Document";
}
