<script lang="ts">
  /**
   * Score viewer: one page at a time, fitted to the available space.
   *
   * No persistent toolbar. Tap the right side (or swipe left) for the next
   * page, the left side for the previous one, the top strip for the menu.
   * Keys: Space / → / PageDown next, Shift+Space / ← / PageUp previous,
   * Home / End, F fullscreen.
   *
   * Each page renders once into an off-screen canvas; turning copies it to
   * the visible canvas. After every turn the neighbouring pages render
   * ahead, so turns feel instant.
   */
  import type { PDFDocumentProxy } from 'pdfjs-dist';
  import { onDestroy } from 'svelte';
  import { loadPdfjs } from '$lib/pdf/pdfjs';

  let { url, downloadUrl }: { url: string; downloadUrl: string } = $props();

  let container: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let doc = $state<PDFDocumentProxy | null>(null);
  let pageCount = $state(0);
  let page = $state(1);
  let status = $state<'loading' | 'ready' | 'failed'>('loading');
  let menuOpen = $state(false);
  let immersive = $state(false);
  let jumpTo = $state('');

  const cache = new Map<number, HTMLCanvasElement>();
  let cacheKey = '';
  let renderQueue: Promise<void> = Promise.resolve();
  let loadToken = 0;

  $effect(() => {
    void open(url);
  });

  onDestroy(() => {
    loadToken++;
    void doc?.loadingTask.destroy();
  });

  async function open(source: string) {
    const token = ++loadToken;
    status = 'loading';
    cache.clear();
    page = 1;
    try {
      const lib = await loadPdfjs();
      const loaded = await lib.getDocument({ url: source, withCredentials: true }).promise;
      if (token !== loadToken) return void loaded.loadingTask.destroy();
      void doc?.loadingTask.destroy();
      doc = loaded;
      pageCount = loaded.numPages;
      status = 'ready';
      await show(1);
    } catch {
      if (token === loadToken) status = 'failed';
    }
  }

  /** Size the page should render at: fit inside the container, HiDPI-aware. */
  function targetSize(width: number, height: number) {
    const box = container.getBoundingClientRect();
    const fit = Math.min(box.width / width, box.height / height);
    return { scale: fit * (window.devicePixelRatio || 1), cssWidth: width * fit, cssHeight: height * fit };
  }

  function renderPage(number: number): Promise<HTMLCanvasElement> {
    const cached = cache.get(number);
    if (cached) return Promise.resolve(cached);
    // Serialise renders: one at a time keeps memory flat on tablets.
    const job = renderQueue.then(async () => {
      if (!doc) throw new Error('no document');
      const pdfPage = await doc.getPage(number);
      const base = pdfPage.getViewport({ scale: 1 });
      const { scale } = targetSize(base.width, base.height);
      const viewport = pdfPage.getViewport({ scale });
      const offscreen = document.createElement('canvas');
      offscreen.width = Math.floor(viewport.width);
      offscreen.height = Math.floor(viewport.height);
      await pdfPage.render({ canvas: offscreen, viewport }).promise;
      cache.set(number, offscreen);
      // Keep only pages near the current one.
      for (const key of cache.keys()) if (Math.abs(key - page) > 3) cache.delete(key);
      return offscreen;
    });
    renderQueue = job.then(() => undefined, () => undefined);
    return job;
  }

  async function show(number: number) {
    if (!doc) return;
    const target = Math.min(Math.max(1, number), pageCount);
    page = target;
    const key = `${container.clientWidth}x${container.clientHeight}`;
    if (key !== cacheKey) {
      cache.clear();
      cacheKey = key;
    }
    const rendered = await renderPage(target);
    if (page !== target) return; // the user turned again meanwhile
    const pdfPage = await doc.getPage(target);
    const base = pdfPage.getViewport({ scale: 1 });
    const { cssWidth, cssHeight } = targetSize(base.width, base.height);
    canvas.width = rendered.width;
    canvas.height = rendered.height;
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    canvas.getContext('2d')?.drawImage(rendered, 0, 0);
    // Render ahead: next first (the common direction), then previous.
    if (target < pageCount) void renderPage(target + 1).catch(() => {});
    if (target > 1) void renderPage(target - 1).catch(() => {});
  }

  const next = () => page < pageCount && show(page + 1);
  const previous = () => page > 1 && show(page - 1);

  // --- Input --------------------------------------------------------------

  let pointerStart: { x: number; y: number } | null = null;

  function onPointerDown(event: PointerEvent) {
    pointerStart = { x: event.clientX, y: event.clientY };
  }

  function onPointerUp(event: PointerEvent) {
    if (!pointerStart || status !== 'ready') return;
    const dx = event.clientX - pointerStart.x;
    const dy = event.clientY - pointerStart.y;
    pointerStart = null;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
      void (dx < 0 ? next() : previous());
      return;
    }
    const box = container.getBoundingClientRect();
    if (event.clientY - box.top < box.height * 0.15) {
      menuOpen = !menuOpen;
      return;
    }
    menuOpen = false;
    void (event.clientX - box.left < box.width / 2 ? previous() : next());
  }

  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable]') || status !== 'ready') return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const forward = ['ArrowRight', 'ArrowDown', 'PageDown'].includes(event.key) || (event.key === ' ' && !event.shiftKey);
    const back = ['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key) || (event.key === ' ' && event.shiftKey);
    if (forward) void next();
    else if (back) void previous();
    else if (event.key === 'Home') void show(1);
    else if (event.key === 'End') void show(pageCount);
    else if (event.key === 'f' || event.key === 'F') void toggleFullscreen();
    else if (event.key === 'Escape' && immersive && !document.fullscreenElement) immersive = false;
    else return;
    event.preventDefault();
  }

  async function toggleFullscreen() {
    menuOpen = false;
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    // Real fullscreen where allowed; otherwise a viewport-filling overlay
    // (older iPad Safari has no element fullscreen).
    try {
      await container.parentElement?.requestFullscreen();
    } catch {
      immersive = !immersive;
    }
  }

  function jump(event: SubmitEvent) {
    event.preventDefault();
    const number = Number(jumpTo);
    if (Number.isInteger(number) && number >= 1 && number <= pageCount) void show(number);
    jumpTo = '';
    menuOpen = false;
  }

  // Re-fit after resizes and fullscreen changes.
  let resizeTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const observer = new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => status === 'ready' && void show(page), 120);
    });
    observer.observe(container);
    return () => observer.disconnect();
  });
</script>

<svelte:window onkeydown={onKeydown} />
<svelte:document onfullscreenchange={() => status === 'ready' && void show(page)} />

<div
  class="viewer relative bg-clef-charcoal select-none {immersive ? 'fixed inset-0 z-50' : 'h-full w-full'}"
  aria-label="Score viewer"
>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    bind:this={container}
    onpointerdown={onPointerDown}
    onpointerup={onPointerUp}
    class="absolute inset-0 flex items-center justify-center overflow-hidden cursor-pointer"
    style="touch-action: manipulation"
  >
    <canvas bind:this={canvas} class="block bg-white shadow-lg {status === 'ready' ? '' : 'invisible'}"></canvas>
    {#if status === 'loading'}
      <p class="absolute text-clef-stone-300/70 text-sm">Loading score…</p>
    {:else if status === 'failed'}
      <p class="absolute text-clef-claret text-sm">This score couldn't be opened.</p>
    {/if}
  </div>

  {#if status === 'ready'}
    <div class="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-xs tabular-nums text-clef-stone-100">
      {page} / {pageCount}
    </div>
  {/if}

  {#if menuOpen}
    <div class="absolute top-3 left-1/2 -translate-x-1/2 flex flex-wrap items-center gap-2 rounded-lg border border-clef-graphite-500 bg-clef-charcoal/95 px-3 py-2 text-sm shadow-xl">
      <form onsubmit={jump} class="flex items-center gap-1">
        <label for="page-jump" class="text-clef-stone-300">Page</label>
        <input
          id="page-jump"
          bind:value={jumpTo}
          inputmode="numeric"
          placeholder={String(page)}
          class="w-14 rounded border border-clef-graphite-500 bg-clef-graphite-700 px-2 py-1 text-center"
        />
        <span class="text-clef-stone-300/70">of {pageCount}</span>
      </form>
      <button type="button" onclick={toggleFullscreen} class="rounded px-2 py-1 hover:bg-clef-graphite-700">Fullscreen</button>
      <a href={downloadUrl} class="rounded px-2 py-1 hover:bg-clef-graphite-700">Download</a>
      <button type="button" onclick={() => (menuOpen = false)} class="rounded px-2 py-1 text-clef-stone-300 hover:bg-clef-graphite-700" aria-label="Close menu">✕</button>
    </div>
  {/if}
</div>
