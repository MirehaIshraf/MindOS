export type DocumentTextExtractionResult = {
  ok: boolean;
  text: string;
  chars: number;
  file_type: "text" | "pdf" | "docx";
  page_count?: number;
  warnings: string[];
  error?: string;
};

export type DocumentExtractionOptions = {
  maxCharsPerFile: number;
};

export function truncateExtractedText(
  text: string,
  maxChars: number,
  warnings: string[],
): { text: string; chars: number } {
  if (text.length <= maxChars) {
    return { text, chars: text.length };
  }
  warnings.push(`Text was truncated to ${maxChars.toLocaleString()} characters for this file.`);
  const truncated = text.slice(0, maxChars);
  return { text: truncated, chars: truncated.length };
}
