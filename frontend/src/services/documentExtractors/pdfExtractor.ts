import * as pdfjsLib from "pdfjs-dist";

import { truncateExtractedText, type DocumentExtractionOptions, type DocumentTextExtractionResult } from "./types";

const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.mjs", import.meta.url).toString();
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

type PdfTextItem = {
  str?: string;
};

export async function extractPdfText(file: File, options: DocumentExtractionOptions): Promise<DocumentTextExtractionResult> {
  const warnings: string[] = [];
  try {
    const buffer = await file.arrayBuffer();
    const document = await pdfjsLib.getDocument({ data: buffer }).promise;
    const pageTexts: string[] = [];
    let collected = 0;

    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      if (collected >= options.maxCharsPerFile) break;
      const page = await document.getPage(pageNumber);
      const textContent = await page.getTextContent();
      const text = textContent.items
        .map((item) => String((item as PdfTextItem).str ?? ""))
        .filter(Boolean)
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      if (text) {
        const pageBlock = `--- Page ${pageNumber} ---\n\n${text}`;
        pageTexts.push(pageBlock);
        collected += pageBlock.length + 2;
      }
    }

    const extracted = pageTexts.join("\n\n").trim();
    if (!extracted) {
      return {
        ok: false,
        text: "",
        chars: 0,
        file_type: "pdf",
        page_count: document.numPages,
        warnings,
        error: "No selectable text found. This PDF may be scanned/image-based.",
      };
    }

    const truncated = truncateExtractedText(extracted, options.maxCharsPerFile, warnings);
    if (document.numPages > pageTexts.length) {
      warnings.push("Only part of this PDF was extracted because the per-file character limit was reached.");
    }
    return {
      ok: true,
      text: truncated.text,
      chars: truncated.chars,
      file_type: "pdf",
      page_count: document.numPages,
      warnings,
    };
  } catch (error) {
    return {
      ok: false,
      text: "",
      chars: 0,
      file_type: "pdf",
      warnings,
      error: error instanceof Error ? error.message : "Could not extract PDF text.",
    };
  }
}
