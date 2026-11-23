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

export type Line = { text: string; size: number; top: number; left: number; right: number };

/** Group positioned text items into visual lines, top of page first. */
async function firstPageLines(doc: PDFDocumentProxy): Promise<{ lines: Line[]; width: number; height: number }> {
  const page = await doc.getPage(1);
  const { width, height } = page.getViewport({ scale: 1 });
  const content = await page.getTextContent();
  const pieces: Line[] = [];
  for (const item of content.items) {
    if (!('str' in item) || !isReadableText(item.str)) continue;
    const x = item.transform[4];
    pieces.push({
      text: item.str,
      size: Math.abs(item.height) || Math.abs(item.transform[3]),
      top: height - item.transform[5], // PDF y grows upward
      left: x,
      right: x + item.width
    });
  }
  return { lines: groupLines(pieces), width, height };
}

/**
 * Join positioned text pieces into visual lines, top of page first. Pieces
 * join only when they share a row AND sit close together: a lyricist at the
 * left margin and the composer at the right are two lines, not one.
 */
export function groupLines(pieces: Line[]): Line[] {
  // Left to right, so each line's text is built in reading order. Rows are
  // matched by vertical tolerance, since baselines jitter by fractions of a point.
  const sorted = [...pieces].sort((a, b) => a.left - b.left);
  const lines: Line[] = [];
  for (const piece of sorted) {
    const line = lines.find((l) => {
      // Horizontal gap on whichever side the piece falls (negative = overlap).
      const gap = Math.max(piece.left - l.right, l.left - piece.right);
      return (
        Math.abs(l.top - piece.top) < Math.max(2, piece.size * 0.4) &&
        gap < Math.max(l.size, piece.size) * 3
      );
    });
    if (line) {
      line.text += (piece.left > line.right + piece.size * 0.2 ? ' ' : '') + piece.text;
      line.size = Math.max(line.size, piece.size);
      line.left = Math.min(line.left, piece.left);
      line.right = Math.max(line.right, piece.right);
    } else {
      lines.push({ ...piece });
    }
  }
  return lines
    .map((l) => ({ ...l, text: l.text.replace(/\s+/g, ' ').trim() }))
    .filter((l) => l.text)
    .sort((a, b) => a.top - b.top);
}

const CREDIT = /^(?:music\s+by|composed\s+by|composer|words\s+and\s+music\s+by|by)\s*:?\s+(.+)$/i;
const ARRANGER = /^(?:arr(?:\.|anged)?(?:\s+by)?|arrangement(?:\s+by)?)\s*:?\s+(.+)$/i;
// Tempo marks and lyric credits look like right-aligned credits; skip them.
// Catalogue numbers ("Opus 10 No. 5", "BWV 1009", "D. 328") sit in the same
// right-aligned spot as the composer.
const NOT_A_NAME =
  /^(?:lyrics|words|text)\b|=|\d+\s*bpm|allegr|andante|adagio|moderato|largo|presto|lento|^(?:op(?:us)?\.?|no\.?|nr\.?|bwv|hwv|twv|d\.|k\.|kv|l\.|wo[o0])\s*\d/i;

/** Drop a trailing life-span like "(1810–1849)" or "1810-1849". */
function stripDates(name: string): string {
  return name.replace(/\(?\s*\d{4}\s*[-–—]\s*\d{2,4}\s*\)?\s*$/, '').trim();
}

// Letter, optional accidental ("flat", "-sharp", "♭", "#", or a "b" glued to
// the letter), then the mode. The letter must start a word, so "Ode major"
// doesn't match.
const KEY_PATTERN =
  /(?:^|[^\p{L}])([A-Ga-g])(?:\s*-?\s*(flat|sharp)|\s*([♭♯])|(b|#)(?=\s))?\s+(major|minor|maj\.|min\.)/iu;

// German key names, standard on European editions: "Ges-Dur", "h-moll",
// "Fis-Moll". -es/-s means flat, -is sharp; H is B natural and B is B flat.
const GERMAN_KEY_PATTERN =
  /(?:^|[^\p{L}])(ces|ges|des|as|es|b|fis|cis|gis|dis|ais|eis|[cdefgah])\s*-?\s*(dur|moll)(?!\p{L})/iu;
const GERMAN_TONIC: Record<string, string> = {
  ces: 'Cb', ges: 'Gb', des: 'Db', as: 'Ab', es: 'Eb', b: 'Bb',
  fis: 'F#', cis: 'C#', gis: 'G#', dis: 'D#', ais: 'A#', eis: 'E#',
  c: 'C', d: 'D', e: 'E', f: 'F', g: 'G', a: 'A', h: 'B'
};

function findGermanKey(text: string): string | undefined {
  const match = GERMAN_KEY_PATTERN.exec(text);
  if (!match) return undefined;
  const value = `${GERMAN_TONIC[match[1].toLowerCase()]} ${match[2].toLowerCase() === 'dur' ? 'major' : 'minor'}`;
  return (KEY_SIGNATURES as readonly string[]).includes(value) ? value : undefined;
}

/** Find "in G-flat major", "Gb Major", "c minor", "Ges-Dur"... as an enum value. */
export function findKey(text: string): string | undefined {
  const match = KEY_PATTERN.exec(text);
  if (!match) return findGermanKey(text);
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
  const fromText = suggestFromLines(lines, width, height);
  return {
    // Embedded metadata wins; the page text fills whatever it left empty.
    ...fromText,
    ...(suggestions.title ? { title: suggestions.title } : {}),
    ...(suggestions.composer ? { composer: suggestions.composer } : {})
  };
}

/**
 * True for lines made of words. Engraving tools (LilyPond, Mutopia's
 * source) print music symbols as text in a music font: measure numbers,
 * time signatures ("3 4"), dynamics. Those are often the largest "text"
 * on the page, so title and composer guesses must skip them.
 */
function isWordy(text: string): boolean {
  // Judge names without their life dates: "Chopin (1810 - 1849)" is words.
  const core = stripDates(text);
  const letters = core.match(/\p{L}/gu)?.length ?? 0;
  const visible = core.replace(/\s/g, '').length;
  // At least one real word: "P PP P" (dynamics) is letters but not words.
  return /\p{L}{3,}/u.test(core) && letters / Math.max(visible, 1) >= 0.6;
}

// Music fonts (LilyPond's Emmentaler and friends) map glyphs to control or
// private-use code points, and dynamics to letters ("pp", "mf", "sfz").
const MUSIC_GLYPHS = /[\p{Cc}\p{Co}\uFFFD]/u;
const DYNAMICS = /^(?:p{1,4}|f{1,4}|mp|mf|sfz?|sf{1,2}z?|fp|rfz?)$/i;

/**
 * True for a text item worth reading. Drops music-font glyphs before items
 * are merged into lines, because a tempo mark and the glyphs beside it share
 * one visual row ("Andante" + clef + "pp").
 */
export function isReadableText(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.length >= 2 && !MUSIC_GLYPHS.test(trimmed) && !DYNAMICS.test(trimmed);
}

/** Title, composer, arranger and key guesses from first-page text lines. */
export function suggestFromLines(lines: Line[], width: number, height: number): Suggestions {
  const suggestions: Suggestions = {};
  if (!lines.length) return suggestions; // a scan: nothing to read

  const header = lines.filter((l) => l.top < height * 0.4 && isWordy(l.text));

  // Titles are centred; instrument labels ("Cembalo.") hug the left margin.
  const centred = header.filter((l) => Math.abs((l.left + l.right) / 2 - width / 2) < width * 0.15);
  const titlePool = centred.length ? centred : header;
  if (titlePool.length) {
    const largest = Math.max(...titlePool.map((l) => l.size));
    const titleLines = titlePool.filter((l) => l.size >= largest * 0.95 && !CREDIT.test(l.text));
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

  const key = findKey(lines.map((l) => l.text).join('\n'));
  if (key) suggestions.key = { value: key, source: 'page-text' };

  return suggestions;
}
