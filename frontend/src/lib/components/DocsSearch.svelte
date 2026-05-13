<!--
  DocsSearch — small client-side search input over the docs route tree.
  Index lives in $lib/docs/search-index.ts and is built at module load
  via Vite's `import.meta.glob`. Boosts: title 3×, description 2×,
  headings 2×, body 1×.

  Distinct from the eventual ⌘K score search (a feature of the running
  library, not the docs). Ticket 0153.
-->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { searchDocs, type SearchHit } from '$lib/docs/search-index';

  let query = $state('');
  let results = $state<SearchHit[]>([]);
  let activeIndex = $state(0);
  let inputEl: HTMLInputElement | undefined = $state();

  $effect(() => {
    results = searchDocs(query);
    activeIndex = 0;
  });

  function pick(hit: SearchHit) {
    query = '';
    results = [];
    inputEl?.blur();
    goto(hit.id);
  }

  function onKeydown(e: KeyboardEvent) {
    if (results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % results.length;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + results.length) % results.length;
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(results[activeIndex]);
    } else if (e.key === 'Escape') {
      query = '';
      results = [];
      inputEl?.blur();
    }
  }
</script>

<div class="relative">
  <input
    bind:this={inputEl}
    bind:value={query}
    onkeydown={onKeydown}
    type="search"
    placeholder="Search docs…"
    aria-label="Search docs"
    class="w-full px-3 py-2 text-sm rounded bg-clef-charcoal border border-clef-graphite-500 focus:border-clef-claret focus:outline-none placeholder:text-clef-stone-300/50"
  />

  {#if results.length > 0}
    <ul
      role="listbox"
      class="absolute left-0 right-0 mt-1 rounded-md bg-clef-graphite-700 border border-clef-graphite-500 shadow-lg z-50 max-h-96 overflow-y-auto"
    >
      {#each results as hit, i (hit.id)}
        <li role="option" aria-selected={i === activeIndex}>
          <button
            type="button"
            onclick={() => pick(hit)}
            onmouseenter={() => (activeIndex = i)}
            class="block w-full text-left px-3 py-2 text-sm hover:bg-clef-graphite-500 {i ===
            activeIndex
              ? 'bg-clef-graphite-500'
              : ''}"
          >
            <div class="text-clef-ivory">{hit.title}</div>
            {#if hit.description}
              <div class="text-xs text-clef-stone-300/70 truncate">
                {hit.description}
              </div>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {:else if query.trim().length > 0}
    <div
      class="absolute left-0 right-0 mt-1 rounded-md bg-clef-graphite-700 border border-clef-graphite-500 shadow-lg z-50 px-3 py-2 text-sm text-clef-stone-300/70"
    >
      No matches.
    </div>
  {/if}
</div>
