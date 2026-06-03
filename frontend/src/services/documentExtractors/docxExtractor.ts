import mammoth from "mammoth/mammoth.browser";

import { truncateExtractedText, type DocumentExtractionOptions, type DocumentTextExtractionResult } from "./types";

type MammothMessage = {
  message?: string;
};

type MammothRawTextResult = {
  value?: string;
  messages?: MammothMessage[];
};

type MammothBrowser = {
  extractRawText: (input: { arrayBuffer: ArrayBuffer }) => Promise<MammothRawTextResult>;
};

export async function extractDocxText(file: File, options: DocumentExtractionOptions): Promise<DocumentTextExtractionResult> {
  const warnings: string[] = [];
  try {
    const arrayBuffer = await file.arrayBuffer();
    const result = await (mammoth as MammothBrowser).extractRawText({ arrayBuffer });
    for (const message of result.messages ?? []) {
      if (message.message) warnings.push(message.message);
    }
    const text = (result.value ?? "").replace(/\n{3,}/g, "\n\n").trim();
    if (!text) {
      return {
        ok: false,
        text: "",
        chars: 0,
        file_type: "docx",
        warnings,
        error: "Could not extract text from this DOCX.",
      };
    }
    const truncated = truncateExtractedText(text, options.maxCharsPerFile, warnings);
    return {
      ok: true,
      text: truncated.text,
      chars: truncated.chars,
      file_type: "docx",
      warnings,
    };
  } catch (error) {
    return {
      ok: false,
      text: "",
      chars: 0,
      file_type: "docx",
      warnings,
      error: error instanceof Error ? error.message : "Could not extract DOCX text.",
    };
  }
}
