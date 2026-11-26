<script lang="ts">
  /**
   * Append one piece (and the part being viewed) to a setlist the user can
   * add to, or to a new one named here. A shared setlist takes only pieces
   * you own, so it's offered only for those (`owned`).
   */
  import { api, setlistErrorMessage, type SetlistDetail, type SetlistSummary } from '$lib/api';

  let {
    open = $bindable(false),
    arrangementId,
    partId,
    owned,
    onAdded
  }: {
    open?: boolean;
    arrangementId: string;
    /** The part to open from the setlist; null follows the cover part. */
    partId: string | null;
    /** The viewer owns this piece. */
    owned: boolean;
    onAdded: (setlist: SetlistDetail) => void;
  } = $props();

  let dialog: HTMLDialogElement;
  let setlists = $state<SetlistSummary[] | null>(null);
  let chosen = $state('');
  let newName = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  const NEW = '__new__';

  $effect(() => {
    if (open && !dialog.open) {
      dialog.showModal();
      void load();
    }
    if (!open && dialog.open) dialog.close();
  });

  async function load() {
    try {
      const all = await api.get<SetlistSummary[]>('/api/v1/setlists');
      setlists = all.filter((s) => s.can_edit && (owned || !s.shared));
      chosen = setlists[0]?.id ?? NEW;
    } catch {
      error = 'Could not load setlists.';
    }
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      let target = chosen;
      if (chosen === NEW) {
        if (!newName.trim()) return;
        target = (await api.post<SetlistDetail>('/api/v1/setlists', { name: newName.trim() })).id;
      }
      const updated = await api.post<SetlistDetail>(`/api/v1/setlists/${target}/items`, {
        arrangement_id: arrangementId,
        part_id: partId
      });
      onAdded(updated);
      open = false;
    } catch (e) {
      error = setlistErrorMessage(e);
    } finally {
      busy = false;
    }
  }
</script>

<dialog
  bind:this={dialog}
  onclose={() => {
    open = false;
    newName = '';
    error = null;
  }}
  oncancel={(e) => busy && e.preventDefault()}
  class="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-lg border border-clef-graphite-500 bg-clef-charcoal text-clef-stone-100 p-0 backdrop:bg-black/70"
>
  <form onsubmit={submit} class="p-6 space-y-4 text-sm">
    <h2 class="text-xl font-serif font-semibold">Add to setlist</h2>
    {#if setlists === null && !error}
      <p class="text-clef-stone-300/70">Loading…</p>
    {:else}
      <fieldset class="space-y-2">
        <legend class="sr-only">Setlist</legend>
        {#each setlists ?? [] as setlist (setlist.id)}
          <label class="flex items-center gap-2">
            <input type="radio" bind:group={chosen} value={setlist.id} class="accent-clef-claret" />
            <span class="flex-1 truncate">{setlist.name}</span>
            <span class="text-xs text-clef-stone-300/70">{setlist.item_count}</span>
          </label>
        {/each}
        <label class="flex items-center gap-2">
          <input type="radio" bind:group={chosen} value={NEW} class="accent-clef-claret" />
          <span>New setlist</span>
        </label>
        {#if chosen === NEW}
          <input bind:value={newName} maxlength="200" required placeholder="Name, e.g. Spring recital" class="oc-field" />
        {/if}
      </fieldset>
    {/if}
    {#if error}<p class="text-clef-claret">{error}</p>{/if}
    <div class="flex justify-end gap-2">
      <button type="button" onclick={() => (open = false)} disabled={busy} class="px-4 py-2 rounded text-clef-stone-300 hover:text-clef-ivory">Cancel</button>
      <button type="submit" disabled={busy || setlists === null} class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50">
        {busy ? 'Adding…' : 'Add'}
      </button>
    </div>
  </form>
</dialog>
