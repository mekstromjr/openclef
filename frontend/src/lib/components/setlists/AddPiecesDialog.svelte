<script lang="ts">
  /**
   * Pick pieces from the library to append to a setlist. Uses the library
   * search endpoint, so results narrow as you type. Selection order is the
   * order the pieces are added in.
   */
  import { api, type ArrangementList, type ArrangementSummary } from '$lib/api';

  let {
    open = $bindable(false),
    onAdd
  }: { open?: boolean; onAdd: (pieces: ArrangementSummary[]) => void } = $props();

  let dialog: HTMLDialogElement;
  let query = $state('');
  let results = $state<ArrangementSummary[]>([]);
  let total = $state(0);
  let picked = $state<ArrangementSummary[]>([]);
  let error = $state<string | null>(null);
  let searchToken = 0;

  $effect(() => {
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  // Search as the user types (debounced).
  $effect(() => {
    if (!open) return;
    const q = query.trim();
    const token = ++searchToken;
    const timer = setTimeout(async () => {
      // Best matches first while searching; alphabetical when browsing.
      const params = new URLSearchParams({ page_size: '20', sort: q ? 'relevance' : 'title' });
      if (q) params.set('q', q);
      try {
        const list = await api.get<ArrangementList>(`/api/v1/arrangements?${params}`);
        if (token !== searchToken) return;
        results = list.items;
        total = list.total;
        error = null;
      } catch {
        if (token === searchToken) error = 'Search failed.';
      }
    }, 150);
    return () => clearTimeout(timer);
  });

  function toggle(piece: ArrangementSummary) {
    picked = picked.some((p) => p.id === piece.id) ? picked.filter((p) => p.id !== piece.id) : [...picked, piece];
  }

  function add(event: SubmitEvent) {
    event.preventDefault();
    if (picked.length) onAdd(picked);
    open = false;
  }

  function reset() {
    query = '';
    picked = [];
    error = null;
  }
</script>

<dialog
  bind:this={dialog}
  onclose={() => {
    open = false;
    reset();
  }}
  class="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-lg border border-clef-graphite-500 bg-clef-charcoal text-clef-stone-100 p-0 backdrop:bg-black/70"
>
  <form onsubmit={add} class="p-6 space-y-4 text-sm">
    <h2 class="text-xl font-serif font-semibold">Add pieces</h2>
    <label class="block">
      <span class="sr-only">Search the library</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={query} type="search" placeholder="Search title, composer, instrument…" autofocus class="oc-field" />
    </label>

    {#if error}
      <p class="text-clef-claret">{error}</p>
    {:else}
      <ul class="max-h-80 overflow-y-auto divide-y divide-clef-graphite-500 rounded border border-clef-graphite-500">
        {#each results as piece (piece.id)}
          {@const order = picked.findIndex((p) => p.id === piece.id)}
          <li>
            <label class="flex cursor-pointer items-center gap-3 px-3 py-2 hover:bg-clef-graphite-700">
              <input type="checkbox" checked={order >= 0} onchange={() => toggle(piece)} class="accent-clef-claret" />
              <span class="min-w-0 flex-1">
                <span class="block truncate">{piece.title}</span>
                <span class="block truncate text-xs text-clef-stone-300/70">{piece.composer.join(' · ')}</span>
              </span>
              {#if order >= 0}<span class="text-xs tabular-nums text-clef-claret">{order + 1}</span>{/if}
            </label>
          </li>
        {:else}
          <li class="px-3 py-6 text-center text-clef-stone-300/70">{query.trim() ? 'No matches.' : 'The library is empty.'}</li>
        {/each}
      </ul>
      {#if total > results.length}
        <p class="text-xs text-clef-stone-300/70">Showing {results.length} of {total}. Type to narrow the list.</p>
      {/if}
    {/if}

    <div class="flex justify-end gap-2">
      <button type="button" onclick={() => (open = false)} class="px-4 py-2 rounded text-clef-stone-300 hover:text-clef-ivory">Cancel</button>
      <button type="submit" disabled={!picked.length} class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50">
        {picked.length ? `Add ${picked.length}` : 'Add'}
      </button>
    </div>
  </form>
</dialog>
