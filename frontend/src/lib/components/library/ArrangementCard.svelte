<script lang="ts">
  import type { ArrangementSummary } from '$lib/api';
  import Difficulty from './Difficulty.svelte';

  let { item, layout = 'grid' }: { item: ArrangementSummary; layout?: 'grid' | 'list' } = $props();

  // Until the score viewer lands (ticket 0140), a card opens the PDF in the
  // browser's own viewer.
  const href = $derived(item.cover_part_id ? `/api/v1/parts/${item.cover_part_id}/file` : undefined);
  const thumbnail = $derived(
    item.cover_part_id && item.cover_thumbnail_ready
      ? `/api/v1/parts/${item.cover_part_id}/thumbnail`
      : null
  );
  const composers = $derived(item.composer.join(' · '));
</script>

{#snippet cover(sizeClass: string)}
  <div class="{sizeClass} shrink-0 rounded bg-clef-ivory/95 overflow-hidden flex items-center justify-center">
    {#if thumbnail}
      <img src={thumbnail} alt="" loading="lazy" class="w-full h-full object-cover object-top" />
    {:else}
      <span class="text-clef-stone-600 text-3xl" aria-hidden="true">𝄞</span>
    {/if}
  </div>
{/snippet}

{#if layout === 'grid'}
  <a
    {href}
    target="_blank"
    rel="noopener"
    class="group block rounded-lg border border-clef-graphite-500 bg-clef-graphite-700/40 p-3 hover:border-clef-claret transition-colors"
  >
    {@render cover('aspect-[3/4] w-full')}
    <div class="mt-3 space-y-1">
      <h3 class="font-serif text-lg leading-snug line-clamp-2 group-hover:text-clef-ivory">{item.title}</h3>
      {#if composers}
        <p class="text-sm text-clef-stone-300/80 line-clamp-1">{composers}</p>
      {/if}
      <div class="flex flex-wrap items-center gap-1 pt-1">
        {#each item.instrumentation as instrument (instrument)}
          <span class="text-xs px-2 py-0.5 rounded-full bg-clef-midnight text-clef-stone-100">{instrument}</span>
        {/each}
        <span class="ml-auto text-xs"><Difficulty value={item.difficulty} /></span>
      </div>
    </div>
  </a>
{:else}
  <a
    {href}
    target="_blank"
    rel="noopener"
    class="group flex items-center gap-4 rounded-lg border border-clef-graphite-500 bg-clef-graphite-700/40 p-2 hover:border-clef-claret transition-colors"
  >
    {@render cover('w-12 h-16')}
    <div class="min-w-0 flex-1">
      <h3 class="font-serif text-base truncate">{item.title}</h3>
      <p class="text-sm text-clef-stone-300/80 truncate">
        {composers}{#if composers && item.instrumentation.length}{' — '}{/if}{item.instrumentation.join(', ')}
      </p>
    </div>
    <span class="text-xs hidden sm:block"><Difficulty value={item.difficulty} /></span>
    {#if item.part_count > 1}
      <span class="text-xs text-clef-stone-300/70 whitespace-nowrap">{item.part_count} parts</span>
    {/if}
  </a>
{/if}
