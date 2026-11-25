<script lang="ts">
  import type { ArrangementSummary } from '$lib/api';
  import { authState } from '$lib/stores/auth.svelte';
  import Difficulty from './Difficulty.svelte';

  let { item, layout = 'grid' }: { item: ArrangementSummary; layout?: 'grid' | 'list' } = $props();

  const href = $derived(`/arrangements/${item.id}`);
  const thumbnail = $derived(
    item.cover_part_id && item.cover_thumbnail_ready
      ? `/api/v1/parts/${item.cover_part_id}/thumbnail`
      : null
  );
  const composers = $derived(item.composer.join(' · '));
  // Someone else's piece in your library: it came through sharing.
  const sharedBy = $derived(
    authState.user && item.owner_id !== authState.user.id ? item.owner_username : null
  );
</script>

{#snippet sharedIcon()}
  {#if sharedBy}
    <span title="Shared by {sharedBy}" class="inline-flex shrink-0 text-clef-stone-300" data-testid="shared-icon">
      <svg viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4" aria-hidden="true">
        <path d="M7 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm6.5 0a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM1 16c0-2.8 2.7-5 6-5s6 2.2 6 5v1H1v-1Zm13 1v-1c0-1.5-.5-2.9-1.4-4 .3 0 .6-.1.9-.1 2.8 0 5 1.8 5 4.1v1H14Z" />
      </svg>
      <span class="sr-only">Shared by {sharedBy}</span>
    </span>
  {/if}
{/snippet}

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
    class="group block rounded-lg border border-clef-graphite-500 bg-clef-graphite-700/40 p-3 hover:border-clef-claret transition-colors"
  >
    {@render cover('aspect-[3/4] w-full')}
    <div class="mt-3 space-y-1">
      <div class="flex items-start gap-2">
        <h3 class="flex-1 font-serif text-lg leading-snug line-clamp-2 group-hover:text-clef-ivory">{item.title}</h3>
        <span class="pt-1">{@render sharedIcon()}</span>
      </div>
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
    class="group flex items-center gap-4 rounded-lg border border-clef-graphite-500 bg-clef-graphite-700/40 p-2 hover:border-clef-claret transition-colors"
  >
    {@render cover('w-12 h-16')}
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <h3 class="font-serif text-base truncate">{item.title}</h3>
        {@render sharedIcon()}
      </div>
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
