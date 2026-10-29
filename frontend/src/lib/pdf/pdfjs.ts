/**
 * Lazy pdf.js loader shared by the upload preview and the score viewer.
 * The library (and its ~1.2 MB worker) downloads on first use only.
 */
let pdfjs: typeof import('pdfjs-dist') | null = null;

export async function loadPdfjs(): Promise<typeof import('pdfjs-dist')> {
  if (!pdfjs) {
    const lib = await import('pdfjs-dist');
    const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
    lib.GlobalWorkerOptions.workerSrc = worker.default;
    pdfjs = lib;
  }
  return pdfjs;
}
