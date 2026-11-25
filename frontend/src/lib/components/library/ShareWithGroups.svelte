<script lang="ts">
  // Share one piece with groups you're in (openclef#63). Shown to the
  // piece's owner only; the server refuses anyone else.
  import { onMount } from 'svelte';
  import { api, type ArrangementDetail, type Group } from '$lib/api';

  let {
    arrangement,
    onSaved
  }: { arrangement: ArrangementDetail; onSaved: (updated: ArrangementDetail) => void } = $props();

  let groups = $state<Group[]>([]);
  let busy = $state(false);
  let error = $state<string | null>(null);

  const sharedWith = $derived(new Set(arrangement.groups.map((g) => g.id)));

  onMount(async () => {
    try {
      groups = await api.get<Group[]>('/api/v1/groups');
    } catch {
      // No group list: the control just doesn't show.
    }
  });

  async function toggle(group: Group, box: HTMLInputElement) {
    const on = box.checked;
    const next = new Set(sharedWith);
    if (on) next.add(group.id);
    else next.delete(group.id);
    busy = true;
    error = null;
    try {
      onSaved(
        await api.put<ArrangementDetail>(`/api/v1/arrangements/${arrangement.id}/shares`, {
          group_ids: [...next]
        })
      );
    } catch {
      box.checked = !on; // put the box back to what's saved
      error = 'Saving failed. Try again.';
    } finally {
      busy = false;
    }
  }
</script>

{#if groups.length}
  <fieldset class="text-xs text-clef-stone-300/80" data-testid="share-with-groups">
    <legend class="sr-only">Share with groups</legend>
    <span class="mr-2">Share with</span>
    {#each groups as group (group.id)}
      <label class="mr-3 inline-flex items-center gap-1">
        <input
          type="checkbox"
          checked={sharedWith.has(group.id)}
          disabled={busy}
          onchange={(e) => toggle(group, e.currentTarget)}
          class="accent-clef-claret"
        />
        {group.name}
      </label>
    {/each}
    {#if error}<span class="text-clef-claret">{error}</span>{/if}
  </fieldset>
{/if}
