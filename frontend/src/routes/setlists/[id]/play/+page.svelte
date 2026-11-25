<script lang="ts">
  /**
   * Play a setlist: one viewer that flows from piece to piece. Turning past
   * the last page opens the next piece; turning back from page 1 opens the
   * previous piece at its last page. The next piece's PDF is fetched while
   * the current one is being read, so the change is immediate.
   *
   * The viewer stays mounted for the whole setlist (fullscreen survives);
   * only its `url` changes. `?at=N` (1-based) records the position, so a
   * reload or a shared link resumes at the same piece.
   */
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { ApiError, api, withoutHidden, type SetlistDetail, type SetlistEntry } from '$lib/api';
  import PdfViewer from '$lib/components/viewer/PdfViewer.svelte';
  import { startIndex } from '$lib/setlists/order';

  let setlist = $state<SetlistDetail | null>(null);
  let error = $state<string | null>(null);
  let index = $state(0);
  let startAt = $state<'first' | 'last'>('first');
  let preloaded = $state<Promise<ArrayBuffer> | null>(null);

  // Prefetched PDFs by part id. Only the upcoming piece is kept.
  const prefetched = new Map<string, Promise<ArrayBuffer>>();

  const entry = $derived<SetlistEntry | null>(setlist?.items[index] ?? null);
  const upcoming = $derived<SetlistEntry | null>(setlist?.items[index + 1] ?? null);
  const fileUrl = (partId: string) => `/api/v1/parts/${partId}/file`;

  async function load(setlistId: string) {
    try {
      // Pieces not shared with this viewer are skipped.
      const loaded = withoutHidden(await api.get<SetlistDetail>(`/api/v1/setlists/${setlistId}`)).setlist;
      setlist = loaded;
      index = startIndex(page.url.searchParams.get('at'), loaded.items.length);
      prefetchUpcoming();
    } catch (e) {
      error = e instanceof ApiError && e.status === 404 ? 'This setlist no longer exists.' : 'Could not load this setlist.';
    }
  }

  // A derived string, so replaceState (which swaps page.url) doesn't re-run
  // the load: the effect only fires when the setlist id itself changes.
  const id = $derived(page.params.id as string);
  $effect(() => {
    void load(id);
  });

  function prefetchUpcoming() {
    const partId = setlist?.items[index + 1]?.effective_part_id;
    for (const key of prefetched.keys()) if (key !== partId) prefetched.delete(key);
    if (partId && !prefetched.has(partId)) {
      const request = fetch(fileUrl(partId), { credentials: 'include' }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.arrayBuffer();
      });
      request.catch(() => prefetched.delete(partId));
      prefetched.set(partId, request);
    }
  }

  function goTo(target: number, at: 'first' | 'last' = 'first') {
    if (!setlist || target < 0 || target >= setlist.items.length) return;
    const partId = setlist.items[target].effective_part_id;
    // A preloaded buffer is consumed by pdf.js, so it opens exactly once.
    preloaded = partId ? (prefetched.get(partId) ?? null) : null;
    if (partId) prefetched.delete(partId);
    startAt = at;
    index = target;
    const url = new URL(page.url);
    url.searchParams.set('at', String(target + 1));
    replaceState(url, {});
    prefetchUpcoming();
  }

  const endLabel = $derived(upcoming ? `Next: ${upcoming.title}` : 'End of setlist');
</script>

<svelte:head><title>{entry ? `${entry.title} · ${setlist?.name}` : 'Setlist'} · OpenClef</title></svelte:head>

{#if error}
  <div class="max-w-3xl mx-auto px-6 py-16 text-center space-y-4">
    <p class="text-clef-stone-300">{error}</p>
    <a href="/setlists" class="text-clef-claret hover:underline">All setlists</a>
  </div>
{:else if setlist && setlist.items.length === 0}
  <div class="max-w-3xl mx-auto px-6 py-16 text-center space-y-4">
    <p class="text-clef-stone-300">This setlist is empty.</p>
    <a href="/setlists/{setlist.id}" class="text-clef-claret hover:underline">Add pieces</a>
  </div>
{:else if setlist && entry}
  <div class="flex flex-col h-[calc(100dvh-3.5rem)]">
    <header class="flex items-center gap-2 px-3 sm:px-5 py-2 border-b border-clef-graphite-500 text-sm">
      <a href="/setlists/{setlist.id}" class="shrink-0 text-clef-stone-300/70 hover:text-clef-ivory" aria-label="Back to {setlist.name}">←</a>
      <button type="button" onclick={() => goTo(index - 1, 'first')} disabled={index === 0} class="shrink-0 rounded px-2 py-1 text-clef-stone-300 hover:text-clef-ivory disabled:opacity-30" aria-label="Previous piece">⏮</button>
      <div class="min-w-0 flex-1 text-center">
        <p class="truncate font-medium">{entry.title}</p>
        <p class="truncate text-xs text-clef-stone-300/70">
          {index + 1} of {setlist.items.length} · {setlist.name}{entry.part_label ? ` · ${entry.part_label}` : ''}
        </p>
      </div>
      <button type="button" onclick={() => goTo(index + 1, 'first')} disabled={!upcoming} class="shrink-0 rounded px-2 py-1 text-clef-stone-300 hover:text-clef-ivory disabled:opacity-30" aria-label="Next piece">⏭</button>
    </header>

    <section class="flex-1 min-h-[60vh]">
      {#if entry.effective_part_id}
        <!-- The fragment makes consecutive repeats of one part distinct URLs,
             so the viewer reopens it at page 1 instead of staying put. -->
        <PdfViewer
          url={`${fileUrl(entry.effective_part_id)}#${index}`}
          downloadUrl={`${fileUrl(entry.effective_part_id)}?download=1`}
          {startAt}
          {preloaded}
          {endLabel}
          onEnd={() => goTo(index + 1, 'first')}
          onStart={() => goTo(index - 1, 'last')}
        >
          {#snippet menu({ close })}
            <label class="flex items-center gap-1">
              <span class="text-clef-stone-300">Piece</span>
              <select
                value={String(index)}
                onchange={(event) => {
                  goTo(Number(event.currentTarget.value));
                  close();
                }}
                class="max-w-[14rem] rounded border border-clef-graphite-500 bg-clef-graphite-700 px-2 py-1"
              >
                {#each setlist?.items ?? [] as item, position (position)}
                  <option value={String(position)}>{position + 1}. {item.title}</option>
                {/each}
              </select>
            </label>
          {/snippet}
        </PdfViewer>
      {:else}
        <div class="h-full flex flex-col items-center justify-center gap-3 text-clef-stone-300">
          <p>“{entry.title}” has no parts to show.</p>
          {#if upcoming}<button type="button" onclick={() => goTo(index + 1)} class="text-clef-claret hover:underline">Skip to {upcoming.title}</button>{/if}
        </div>
      {/if}
    </section>
  </div>
{:else}
  <p class="px-6 py-10 text-sm text-clef-stone-300/70">Loading…</p>
{/if}
