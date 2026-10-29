/**
 * First-page preview and metadata suggestions for a PDF, in the browser.
 *
 * Suggestions come from what the file states in text: the Info dictionary
 * (Title/Author) and the first page's text layer. Scans have no text layer,
 * so they only get a preview. Reading notation (the key signature glyphs)
 * is out of scope here; see the vision-extraction research ticket.
 */
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { KEY_SIGNATURES } from '$lib/api';
import { loadPdfjs } from './pdfjs';

export type Source = 'pdf-info' | 'page-text';

export interface Suggestions {
  title?: { value: string; source: Source };
  composer?: { value: string; source: Source };
  arranger?: { value: string; source: Source };
  key?: { value: string; source: Source };
}

export async function openPdf(file: File): Promise<PDFDocumentProxy> {
  const lib = await loadPdfjs();
  return lib.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
}

/** Render page 1 into `canvas`, `cssWidth` pixels wide (sharp on HiDPI). */
export async function renderFirstPage(doc: PDFDocumentProxy, canvas: HTMLCanvasElement, cssWidth: number) {
  const page = await doc.getPage(1);
  const base = page.getViewport({ scale: 1 });
  const scale = (cssWidth / base.width) * (window.devicePixelRatio || 1);
  const viewport = page.getViewport({ scale });
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${Math.floor((cssWidth * base.height) / base.width)}px`;
  await page.render({ canvas, viewport }).promise;
}

// --- Suggestions ------------------------------------------------------

// Info values that notation and office tools write when nobody set a title.
const JUNK_INFO = /^(untitled|title|score|document\d*|microsoft word.*|.*\.(mus|mscz|sib|pdf|docx?))$/i;

function cleanInfo(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const text = value.trim();
  return text && !JUNK_INFO.test(text) ? text : undefined;
}

type Line = { text: string; size: number; top: number; left: number; right: number };

/** Group positioned text items into visual lines, top of page first. */
async function firstPageLines(doc: PDFDocumentProxy): Promise<{ lines: Line[]; width: number; height: number }> {
  const page = await doc.getPage(1);
  const { width, height } = page.getViewport({ scale: 1 });
  const content = await page.getTextContent();
  const rows: Line[] = [];
  for (const item of content.items) {
    if (!('str' in item) || !item.str.trim()) continue;
    const x = item.transform[4];
    const top = height - item.transform[5]; // PDF y grows upward
    const size = Math.abs(item.height) || Math.abs(item.transform[3]);
    const row = rows.find((r) => Math.abs(r.top - top) < Math.max(2, size * 0.4));
    if (row) {
      row.text += (x > row.right + size * 0.2 ? ' ' : '') + item.str;
      row.size = Math.max(row.size, size);
      row.left = Math.min(row.left, x);
      row.right = Math.max(row.right, x + item.width);
    } else {
      rows.push({ text: item.str, size, top, left: x, right: x + item.width });
    }
  }
  rows.forEach((r) => (r.text = r.text.replace(/\s+/g, ' ').trim()));
  rows.sort((a, b) => a.top - b.top);
  return { lines: rows.filter((r) => r.text), width, height };
}

const CREDIT = /^(?:music\s+by|composed\s+by|composer|words\s+and\s+music\s+by|by)\s*:?\s+(.+)$/i;
const ARRANGER = /^(?:arr(?:\.|anged)?(?:\s+by)?|arrangement(?:\s+by)?)\s*:?\s+(.+)$/i;
// Tempo marks and lyric credits look like right-aligned credits; skip them.
const NOT_A_NAME = /^(?:lyrics|words|text)\b|=|\d+\s*bpm|allegr|andante|adagio|moderato|largo|presto|lento/i;

/** Drop a trailing life-span like "(1810–1849)" or "1810-1849". */
function stripDates(name: string): string {
  return name.replace(/\(?\s*\d{4}\s*[-–—]\s*\d{2,4}\s*\)?\s*$/, '').trim();
}

// Letter, optional accidental ("flat", "-sharp", "♭", "#", or a "b" glued to
// the letter), then the mode. The letter must start a word, so "Ode major"
// doesn't match.
const KEY_PATTERN =
  /(?:^|[^\p{L}])([A-Ga-g])(?:\s*-?\s*(flat|sharp)|\s*([♭♯])|(b|#)(?=\s))?\s+(major|minor|maj\.|min\.)/iu;

/** Find "in G-flat major", "Gb Major", "c minor"... and map to an enum value. */
export function findKey(text: string): string | undefined {
  const match = KEY_PATTERN.exec(text);
  if (!match) return undefined;
  const [, letter, word, symbol, glyph, mode] = match;
  const accidental = (word ?? symbol ?? glyph ?? '').toLowerCase();
  const sign = ['flat', '♭', 'b'].includes(accidental) ? 'b' : ['sharp', '♯', '#'].includes(accidental) ? '#' : '';
  const value = `${letter.toUpperCase()}${sign} ${mode.toLowerCase().startsWith('maj') ? 'major' : 'minor'}`;
  return (KEY_SIGNATURES as readonly string[]).includes(value) ? value : undefined;
}

export async function suggestMetadata(doc: PDFDocumentProxy): Promise<Suggestions> {
  const suggestions: Suggestions = {};

  const { info } = (await doc.getMetadata().catch(() => ({ info: {} }))) as { info: Record<string, unknown> };
  const infoTitle = cleanInfo(info?.Title);
  const infoAuthor = cleanInfo(info?.Author);
  if (infoTitle) suggestions.title = { value: infoTitle, source: 'pdf-info' };
  if (infoAuthor) suggestions.composer = { value: stripDates(infoAuthor), source: 'pdf-info' };

  const { lines, width, height } = await firstPageLines(doc);
  if (!lines.length) return suggestions; // a scan: nothing to read

  const header = lines.filter((l) => l.top < height * 0.4);

  if (!suggestions.title && header.length) {
    const largest = Math.max(...header.map((l) => l.size));
    const titleLines = header.filter((l) => l.size >= largest * 0.95 && !CREDIT.test(l.text));
    if (titleLines.length) {
      // Keep consecutive lines at the title size together (two-line titles).
      const first = titleLines[0];
      const second = titleLines[1];
      const joined = second && second.top - first.top < first.size * 2 ? `${first.text} ${second.text}` : first.text;
      suggestions.title = { value: joined, source: 'page-text' };
    }
  }

  for (const line of header) {
    const arranger = ARRANGER.exec(line.text);
    if (arranger && !suggestions.arranger) {
      suggestions.arranger = { value: stripDates(arranger[1]), source: 'page-text' };
      continue;
    }
    if (suggestions.composer) continue;
    const credit = CREDIT.exec(line.text);
    if (credit) {
      suggestions.composer = { value: stripDates(credit[1]), source: 'page-text' };
      continue;
    }
    // Engravers right-align the composer under the title.
    const rightAligned = line.right > width * 0.8 && line.left > width * 0.5;
    if (rightAligned && line.text !== suggestions.title?.value && !NOT_A_NAME.test(line.text)) {
      suggestions.composer = { value: stripDates(line.text), source: 'page-text' };
    }
  }

  const key = findKey([suggestions.title?.value ?? '', ...lines.map((l) => l.text)].join('\n'));
  if (key) suggestions.key = { value: key, source: 'page-text' };

  return suggestions;
}
