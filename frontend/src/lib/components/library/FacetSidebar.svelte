<script lang="ts">
  import type { FacetCount, FacetName } from '$lib/api';

  let {
    facets,
    isActive,
    onToggle
  }: {
    facets: Record<FacetName, FacetCount[]> | null;
    isActive: (name: FacetName, value: string) => boolean;
    onToggle: (name: FacetName, value: string) => void;
  } = $props();

  const SECTIONS: { name: FacetName; label: string }[] = [
    { name: 'instrument', label: 'Instrument' },
    { name: 'composer', label: 'Composer' },
    { name: 'key', label: 'Key' },
    { name: 'period', label: 'Period' },
    { name: 'difficulty', label: 'Difficulty' },
    { name: 'tag', label: 'Tag' }
  ];

  function display(name: FacetName, value: string): string {
    return name === 'difficulty' ? '★'.repeat(Number(value)) : value;
  }
</script>

<nav aria-label="Filters" class="space-y-5 text-sm">
  {#each SECTIONS as section (section.name)}
    {@const entries = facets?.[section.name] ?? []}
    {#if entries.length}
      <section>
        <h2 class="text-xs uppercase tracking-wider text-clef-stone-300/60 mb-2">{section.label}</h2>
        <ul class="space-y-0.5">
          {#each entries as entry (entry.value)}
            {@const active = isActive(section.name, entry.value)}
            <li>
              <button
                type="button"
                onclick={() => onToggle(section.name, entry.value)}
                aria-pressed={active}
                class="w-full flex items-center justify-between gap-2 px-2 py-1 rounded text-left hover:bg-clef-graphite-700 {active
                  ? 'bg-clef-claret/20 text-clef-ivory'
                  : 'text-clef-stone-300'}"
              >
                <span class="truncate {section.name === 'difficulty' ? 'text-clef-gold' : ''}">
                  {display(section.name, entry.value)}
                </span>
                <span class="text-xs tabular-nums text-clef-stone-300/60">{entry.count}</span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/each}
</nav>
