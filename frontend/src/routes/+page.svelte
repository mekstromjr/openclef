<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api, type ArrangementList, type FacetName } from '$lib/api';
  import ArrangementCard from '$lib/components/library/ArrangementCard.svelte';
  import FacetSidebar from '$lib/components/library/FacetSidebar.svelte';
  import UploadDialog from '$lib/components/library/UploadDialog.svelte';

  const PAGE_SIZE = 24;
  // Filters that hold one value at a time; `instrument` can repeat ("has all").
  const SINGLE_VALUE: FacetName[] = ['composer', 'key', 'period', 'difficulty', 'tag'];

  let result = $state<ArrangementList | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let uploadOpen = $state(false);
  let layout = $state<'grid' | 'list'>('grid');
  let searchText = $state(page.url.searchParams.get('q') ?? '');

  // Everything the list shows comes from the URL, so a filtered view can be
  // bookmarked or shared and the back button undoes a filter.
  const params = $derived(page.url.searchParams);
  const pageNumber = $derived(Math.max(1, Number(params.get('page')) || 1));
  const filtered = $derived(
    Boolean(params.get('q')) || params.has('instrument') || SINGLE_VALUE.some((name) => params.has(name))
  );
  const pages = $derived(result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1);
  const activeFilterCount = $derived(
    params.getAll('instrument').length + SINGLE_VALUE.filter((name) => params.has(name)).length
  );

  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let pollsLeft = 0;

  async function load(search: URLSearchParams, poll = false) {
    clearTimeout(pollTimer);
    if (!poll) {
      loading = true;
      pollsLeft = 10;
    }
    const query = new URLSearchParams(search);
    query.set('page_size', String(PAGE_SIZE));
    try {
      result = await api.get<ArrangementList>(`/api/v1/arrangements?${query}`);
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
    // New uploads get their cover from the worker a moment later: check back.
    const waitingForCovers = result?.items.some((i) => i.cover_part_id && !i.cover_thumbnail_ready);
    if (waitingForCovers && pollsLeft-- > 0) {
      pollTimer = setTimeout(() => load(search, true), 3000);
    }
  }

  $effect(() => {
    void load(params);
    return () => clearTimeout(pollTimer);
  });

  function navigate(next: URLSearchParams) {
    const qs = next.toString();
    goto(qs ? `?${qs}` : '/', { replaceState: true, keepFocus: true, noScroll: true });
  }

  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  function onSearchInput() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const next = new URLSearchParams(params);
      const q = searchText.trim();
      if (q) next.set('q', q);
      else next.delete('q');
      next.delete('page');
      navigate(next);
    }, 250);
  }

  function isActive(name: FacetName, value: string): boolean {
    return params.getAll(name).includes(value);
  }

  function toggleFacet(name: FacetName, value: string) {
    const next = new URLSearchParams(params);
    const current = next.getAll(name);
    next.delete(name);
    if (name === 'instrument') {
      const values = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
      values.forEach((v) => next.append(name, v));
    } else if (!current.includes(value)) {
      next.set(name, value);
    }
    next.delete('page');
    navigate(next);
  }

  function clearFilters() {
    searchText = '';
    navigate(new URLSearchParams());
  }

  function goToPage(n: number) {
    const next = new URLSearchParams(params);
    if (n > 1) next.set('page', String(n));
    else next.delete('page');
    navigate(next);
    window.scrollTo({ top: 0 });
  }
</script>

<svelte:head><title>Library · OpenClef</title></svelte:head>

<div class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
  <div class="flex flex-wrap items-center gap-3">
    <input
      type="search"
      bind:value={searchText}
      oninput={onSearchInput}
      placeholder="Search title, composer, arranger, instrument…"
      aria-label="Search the library"
      class="flex-1 min-w-[14rem] px-4 py-2 rounded-lg bg-clef-graphite-700/60 border border-clef-graphite-500 focus:border-clef-claret focus:outline-none"
    />
    <div class="flex rounded-lg border border-clef-graphite-500 overflow-hidden text-sm" role="group" aria-label="Layout">
      <button type="button" onclick={() => (layout = 'grid')} aria-pressed={layout === 'grid'} class="px-3 py-2 {layout === 'grid' ? 'bg-clef-graphite-700' : ''}">Grid</button>
      <button type="button" onclick={() => (layout = 'list')} aria-pressed={layout === 'list'} class="px-3 py-2 {layout === 'list' ? 'bg-clef-graphite-700' : ''}">List</button>
    </div>
    <button
      type="button"
      onclick={() => (uploadOpen = true)}
      class="px-4 py-2 rounded-lg bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90"
    >
      Add music
    </button>
  </div>

  {#if error}
    <p class="text-clef-claret text-sm">Couldn't load the library: {error}</p>
  {:else if result && result.total === 0 && !filtered}
    <div class="py-24 text-center space-y-4">
      <p class="text-5xl text-clef-stone-600" aria-hidden="true">𝄞</p>
      <h1 class="text-2xl font-serif">Your library is empty</h1>
      <p class="text-clef-stone-300/70">Add a PDF to start your family's shared shelf of sheet music.</p>
      <button type="button" onclick={() => (uploadOpen = true)} class="px-4 py-2 rounded-lg bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90">
        Add music
      </button>
    </div>
  {:else if result}
    <div class="grid grid-cols-1 md:grid-cols-[13rem_1fr] gap-6">
      <!-- Phones: filters fold away so the pieces come first. -->
      <details class="md:hidden rounded-lg border border-clef-graphite-500 px-3 py-2">
        <summary class="cursor-pointer text-sm text-clef-stone-300">
          Filters{activeFilterCount ? ` (${activeFilterCount})` : ''}
        </summary>
        <div class="pt-3">
          <FacetSidebar facets={result.facets} {isActive} onToggle={toggleFacet} />
        </div>
      </details>
      <aside class="hidden md:block md:sticky md:top-4 md:self-start">
        <FacetSidebar facets={result.facets} {isActive} onToggle={toggleFacet} />
      </aside>

      <section aria-live="polite" class="space-y-4 {loading ? 'opacity-60' : ''}">
        <div class="flex items-center justify-between text-sm text-clef-stone-300/70">
          <span>{result.total} {result.total === 1 ? 'piece' : 'pieces'}</span>
          {#if filtered}
            <button type="button" onclick={clearFilters} class="hover:text-clef-ivory">Clear search and filters</button>
          {/if}
        </div>

        {#if result.items.length === 0}
          <div class="py-16 text-center space-y-3">
            <p class="text-clef-stone-300">Nothing matches.</p>
            <button type="button" onclick={() => (uploadOpen = true)} class="text-clef-claret hover:underline">Add an arrangement</button>
          </div>
        {:else if layout === 'grid'}
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {#each result.items as item (item.id)}<ArrangementCard {item} />{/each}
          </div>
        {:else}
          <div class="space-y-2">
            {#each result.items as item (item.id)}<ArrangementCard {item} layout="list" />{/each}
          </div>
        {/if}

        {#if pages > 1}
          <nav class="flex items-center justify-center gap-4 pt-2 text-sm" aria-label="Pages">
            <button type="button" disabled={pageNumber <= 1} onclick={() => goToPage(pageNumber - 1)} class="px-3 py-1 rounded border border-clef-graphite-500 disabled:opacity-40">Previous</button>
            <span class="text-clef-stone-300/70">Page {pageNumber} of {pages}</span>
            <button type="button" disabled={pageNumber >= pages} onclick={() => goToPage(pageNumber + 1)} class="px-3 py-1 rounded border border-clef-graphite-500 disabled:opacity-40">Next</button>
          </nav>
        {/if}
      </section>
    </div>
  {:else}
    <p class="text-clef-stone-300/70 text-sm">Loading…</p>
  {/if}
</div>

<UploadDialog
  bind:open={uploadOpen}
  knownInstruments={result?.facets.instrument.map((f) => f.value) ?? []}
  onUploaded={() => load(params)}
/>
