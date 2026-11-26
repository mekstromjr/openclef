<script lang="ts">
  import { goto } from '$app/navigation';
  import { api, setlistErrorMessage, type SetlistDetail, type SetlistSummary } from '$lib/api';

  let setlists = $state<SetlistSummary[] | null>(null);
  let loadError = $state<string | null>(null);
  let name = $state('');
  let creating = $state(false);
  let createError = $state<string | null>(null);

  const updated = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

  async function load() {
    try {
      setlists = await api.get<SetlistSummary[]>('/api/v1/setlists');
      loadError = null;
    } catch {
      loadError = 'Could not load setlists.';
    }
  }

  $effect(() => {
    void load();
  });

  async function create(event: SubmitEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    creating = true;
    createError = null;
    try {
      const created = await api.post<SetlistDetail>('/api/v1/setlists', { name: name.trim() });
      await goto(`/setlists/${created.id}`);
    } catch (e) {
      createError = setlistErrorMessage(e);
    } finally {
      creating = false;
    }
  }
</script>

<svelte:head><title>Setlists · OpenClef</title></svelte:head>

<div class="max-w-3xl mx-auto px-4 sm:px-6 py-8 space-y-6">
  <div class="space-y-1">
    <h1 class="font-serif text-3xl">Setlists</h1>
    <p class="text-sm text-clef-stone-300/80">
      A running order for a rehearsal, service or recital. Yours are private until you share them; only a setlist's owner can change it.
    </p>
  </div>

  <form onsubmit={create} class="flex flex-wrap gap-2">
    <label for="new-setlist" class="sr-only">New setlist name</label>
    <input
      id="new-setlist"
      bind:value={name}
      maxlength="200"
      placeholder="New setlist, e.g. Sunday service"
      class="oc-field flex-1 min-w-[12rem]"
    />
    <button
      type="submit"
      disabled={creating || !name.trim()}
      class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50"
    >
      {creating ? 'Creating…' : 'Create'}
    </button>
  </form>
  {#if createError}<p class="text-sm text-clef-claret">{createError}</p>{/if}

  {#if loadError}
    <p class="text-sm text-clef-claret">{loadError}</p>
  {:else if setlists === null}
    <p class="text-sm text-clef-stone-300/70">Loading…</p>
  {:else if setlists.length === 0}
    <p class="text-sm text-clef-stone-300/70">No setlists yet. Name one above to start.</p>
  {:else}
    <ul class="divide-y divide-clef-graphite-500 border-y border-clef-graphite-500">
      {#each setlists as setlist (setlist.id)}
        <li class="flex items-center gap-3 py-3">
          <a href="/setlists/{setlist.id}" class="min-w-0 flex-1 group">
            <span class="block truncate font-medium group-hover:text-clef-claret">{setlist.name}</span>
            <span class="block text-xs text-clef-stone-300/70">
              {setlist.item_count} {setlist.item_count === 1 ? 'piece' : 'pieces'} · {setlist.owner_username}{setlist.shared ? ' · shared' : ''} · {updated(setlist.updated_at)}
            </span>
          </a>
          {#if setlist.item_count > 0}
            <a
              href="/setlists/{setlist.id}/play"
              class="shrink-0 px-3 py-1.5 rounded border border-clef-graphite-500 text-sm hover:border-clef-claret"
            >
              Play
            </a>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
