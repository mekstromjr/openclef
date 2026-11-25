<script lang="ts">
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    ApiError,
    SETLIST_MAX_ITEMS,
    api,
    setlistErrorMessage,
    withoutHidden,
    type ArrangementDetail,
    type ArrangementSummary,
    type Part,
    type SetlistDetail,
    type SetlistEntry
  } from '$lib/api';
  import AddPiecesDialog from '$lib/components/setlists/AddPiecesDialog.svelte';
  import { moveItem, orderChanged, removeItem, toWrite } from '$lib/setlists/order';

  const id = $derived(page.params.id as string);

  let setlist = $state<SetlistDetail | null>(null);
  let entries = $state<SetlistEntry[]>([]);
  /** Entries on this setlist whose piece isn't shared with this viewer. */
  let hidden = $state(0);
  let loadError = $state<string | null>(null);
  let saveError = $state<string | null>(null);
  let saving = $state(false);
  let renaming = $state(false);
  let newName = $state('');
  let addOpen = $state(false);
  let dragFrom = $state<number | null>(null);
  // Rows become draggable only while the grip is held, so the part picker
  // and links inside a row keep working normally.
  let dragArmed = $state<number | null>(null);
  // Parts of each piece, for the "which part opens" picker (editors only).
  let partsByArrangement = $state<Record<string, Part[]>>({});

  const dirty = $derived(setlist ? orderChanged(setlist.items, entries) : false);

  async function load(setlistId: string) {
    try {
      const shown = withoutHidden(await api.get<SetlistDetail>(`/api/v1/setlists/${setlistId}`));
      const loaded = shown.setlist;
      hidden = shown.hidden;
      setlist = loaded;
      entries = loaded.items.map((item) => ({ ...item }));
      loadError = null;
      if (loaded.can_edit) void loadParts(loaded.items.map((item) => item.arrangement_id));
    } catch (e) {
      loadError = e instanceof ApiError && e.status === 404 ? "This setlist doesn't exist or isn't shared with you." : 'Could not load this setlist.';
    }
  }

  async function loadParts(arrangementIds: string[]) {
    const missing = [...new Set(arrangementIds)].filter((aid) => !(aid in partsByArrangement));
    const details = await Promise.all(
      missing.map((aid) => api.get<ArrangementDetail>(`/api/v1/arrangements/${aid}`).catch(() => null))
    );
    const next = { ...partsByArrangement };
    for (const detail of details) if (detail) next[detail.id] = detail.parts;
    partsByArrangement = next;
  }

  $effect(() => {
    void load(id);
  });

  beforeNavigate((navigation) => {
    if (dirty && !saving && !confirm('Leave without saving the new order?')) navigation.cancel();
  });

  function move(from: number, to: number) {
    entries = moveItem(entries, from, to);
  }

  function remove(index: number) {
    entries = removeItem(entries, index);
  }

  function choosePart(index: number, partId: string) {
    const parts = partsByArrangement[entries[index].arrangement_id] ?? [];
    const part = parts.find((p) => p.id === partId) ?? null;
    entries[index] = {
      ...entries[index],
      // The first part is the cover; storing null keeps following the cover.
      part_id: part && part.id !== parts[0]?.id ? part.id : null,
      effective_part_id: part?.id ?? parts[0]?.id ?? null,
      part_label: part?.label ?? parts[0]?.label ?? null,
      page_count: part?.page_count ?? parts[0]?.page_count ?? null
    };
  }

  function addPieces(pieces: ArrangementSummary[]) {
    const room = SETLIST_MAX_ITEMS - entries.length;
    const added = pieces.slice(0, room).map(
      (piece, offset): SetlistEntry => ({
        position: entries.length + offset,
        available: true,
        arrangement_id: piece.id,
        title: piece.title,
        subtitle: piece.subtitle,
        composer: piece.composer,
        part_id: null,
        effective_part_id: piece.cover_part_id,
        part_label: null,
        page_count: null,
        thumbnail_ready: piece.cover_thumbnail_ready
      })
    );
    entries = [...entries, ...added];
    void loadParts(added.map((entry) => entry.arrangement_id));
    if (pieces.length > room) saveError = `A setlist holds at most ${SETLIST_MAX_ITEMS} pieces.`;
  }

  async function save() {
    if (!setlist) return;
    saving = true;
    saveError = null;
    try {
      const saved = await api.put<SetlistDetail>(`/api/v1/setlists/${setlist.id}/items`, {
        items: toWrite(entries),
        expected_updated_at: setlist.updated_at
      });
      setlist = withoutHidden(saved).setlist;
      entries = setlist.items.map((item) => ({ ...item }));
    } catch (e) {
      saveError = setlistErrorMessage(e);
    } finally {
      saving = false;
    }
  }

  async function rename(event: SubmitEvent) {
    event.preventDefault();
    if (!setlist || !newName.trim()) return;
    try {
      const renamed = await api.patch<SetlistDetail>(`/api/v1/setlists/${setlist.id}`, {
        name: newName.trim(),
        expected_updated_at: setlist.updated_at
      });
      // Keep any unsaved reorder; take the new name and version.
      setlist = { ...setlist, name: renamed.name, updated_at: renamed.updated_at };
      renaming = false;
    } catch (e) {
      saveError = setlistErrorMessage(e);
    }
  }

  async function deleteSetlist() {
    if (!setlist || !confirm(`Delete the setlist "${setlist.name}"? The pieces stay in the library.`)) return;
    try {
      await api.delete(`/api/v1/setlists/${setlist.id}`);
      entries = setlist.items; // nothing unsaved to warn about
      await goto('/setlists');
    } catch (e) {
      saveError = setlistErrorMessage(e);
    }
  }

  function onDrop(index: number) {
    if (dragFrom !== null && dragFrom !== index) move(dragFrom, index);
    dragFrom = null;
  }
</script>

<svelte:head><title>{setlist ? `${setlist.name} · OpenClef` : 'OpenClef'}</title></svelte:head>

{#if loadError}
  <div class="max-w-3xl mx-auto px-6 py-16 text-center space-y-4">
    <p class="text-clef-stone-300">{loadError}</p>
    <a href="/setlists" class="text-clef-claret hover:underline">All setlists</a>
  </div>
{:else if setlist}
  <div class="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-5">
    <a href="/setlists" class="text-sm text-clef-stone-300/70 hover:text-clef-ivory">← Setlists</a>

    <div class="flex flex-wrap items-start justify-between gap-3">
      {#if renaming}
        <form onsubmit={rename} class="flex flex-1 flex-wrap gap-2">
          <label for="setlist-name" class="sr-only">Setlist name</label>
          <input id="setlist-name" bind:value={newName} maxlength="200" required class="oc-field flex-1 min-w-[12rem]" />
          <button type="submit" class="px-3 py-1.5 rounded bg-clef-claret text-clef-ivory">Rename</button>
          <button type="button" onclick={() => (renaming = false)} class="px-3 py-1.5 rounded text-clef-stone-300 hover:text-clef-ivory">Cancel</button>
        </form>
      {:else}
        <div class="min-w-0 space-y-1">
          <h1 class="font-serif text-3xl leading-tight">{setlist.name}</h1>
          <p class="text-xs text-clef-stone-300/70">
            {entries.length} {entries.length === 1 ? 'piece' : 'pieces'} · by {setlist.owner_username}
          </p>
        </div>
      {/if}
      <div class="flex flex-wrap gap-2 text-sm">
        {#if entries.length && !dirty}
          <a href="/setlists/{setlist.id}/play" class="px-4 py-1.5 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90">Play</a>
        {/if}
        {#if setlist.can_edit && !renaming}
          <button type="button" onclick={() => (addOpen = true)} class="px-3 py-1.5 rounded border border-clef-graphite-500 hover:border-clef-claret">Add pieces</button>
          <button type="button" onclick={() => { newName = setlist?.name ?? ''; renaming = true; }} class="px-3 py-1.5 rounded border border-clef-graphite-500 hover:border-clef-claret">Rename</button>
        {/if}
      </div>
    </div>

    {#if dirty}
      <div class="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-lg border border-clef-claret/50 bg-clef-charcoal/95 px-3 py-2 text-sm">
        <span class="flex-1 text-clef-stone-300">Unsaved changes to the order.</span>
        <button type="button" onclick={() => setlist && (entries = setlist.items.map((item) => ({ ...item })))} class="px-3 py-1.5 rounded text-clef-stone-300 hover:text-clef-ivory">Discard</button>
        <button type="button" onclick={save} disabled={saving} class="px-4 py-1.5 rounded bg-clef-claret text-clef-ivory font-medium disabled:opacity-50">
          {saving ? 'Saving…' : 'Save order'}
        </button>
      </div>
    {/if}
    {#if saveError}<p class="text-sm text-clef-claret">{saveError}</p>{/if}
    {#if hidden > 0}
      <p class="text-sm text-clef-stone-300/80">
        {hidden} {hidden === 1 ? "piece on this setlist isn't" : "pieces on this setlist aren't"} shared with you, so {hidden === 1 ? "it's" : "they're"} not shown.
      </p>
    {/if}

    {#if entries.length === 0}
      <div class="rounded-lg border border-dashed border-clef-graphite-500 px-6 py-10 text-center text-sm text-clef-stone-300/80 space-y-2">
        <p>This setlist is empty.</p>
        {#if setlist.can_edit}
          <button type="button" onclick={() => (addOpen = true)} class="text-clef-claret hover:underline">Add pieces from the library</button>
        {/if}
      </div>
    {:else}
      <ol class="space-y-2">
        {#each entries as entry, index (`${index}:${entry.arrangement_id}`)}
          {@const parts = partsByArrangement[entry.arrangement_id] ?? []}
          <li
            draggable={setlist.can_edit && dragArmed === index}
            ondragstart={(event) => {
              dragFrom = index;
              // Firefox starts a drag only when some data is set.
              event.dataTransfer?.setData('text/plain', String(index));
              if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
            }}
            ondragover={(event) => dragFrom !== null && event.preventDefault()}
            ondrop={(event) => {
              event.preventDefault();
              onDrop(index);
            }}
            ondragend={() => (dragFrom = dragArmed = null)}
            class="flex items-center gap-3 rounded-lg border px-3 py-2 {dragFrom === index
              ? 'border-clef-claret opacity-60'
              : 'border-clef-graphite-500'}"
          >
            {#if setlist.can_edit}
              <span
                onpointerdown={() => (dragArmed = index)}
                onpointerup={() => (dragArmed = null)}
                class="hidden sm:block shrink-0 cursor-grab select-none px-1 text-clef-stone-300/50 hover:text-clef-ivory"
                aria-hidden="true"
                title="Drag to reorder">⠿</span>
            {/if}
            <span class="w-6 shrink-0 text-right text-sm tabular-nums text-clef-stone-300/70">{index + 1}</span>
            <div class="h-14 w-10 shrink-0 overflow-hidden rounded bg-clef-graphite-700">
              {#if entry.effective_part_id && entry.thumbnail_ready}
                <img src="/api/v1/parts/{entry.effective_part_id}/thumbnail" alt="" class="h-full w-full object-cover object-top" loading="lazy" />
              {/if}
            </div>
            <div class="min-w-0 flex-1">
              <a href="/arrangements/{entry.arrangement_id}" class="block line-clamp-2 break-words font-medium leading-snug hover:text-clef-claret">{entry.title}</a>
              <p class="truncate text-xs text-clef-stone-300/70">{entry.composer.join(' · ')}</p>
              {#if setlist.can_edit && parts.length > 1}
                <label class="mt-1 flex items-center gap-1 text-xs text-clef-stone-300">
                  <span>Opens</span>
                  <select
                    value={entry.effective_part_id ?? ''}
                    onchange={(event) => choosePart(index, event.currentTarget.value)}
                    class="rounded border border-clef-graphite-500 bg-clef-graphite-700 px-1 py-0.5"
                  >
                    {#each parts as part (part.id)}<option value={part.id}>{part.label}</option>{/each}
                  </select>
                </label>
              {:else if entry.part_label}
                <p class="text-xs text-clef-stone-300/70">{entry.part_label}</p>
              {/if}
            </div>
            {#if !dirty}
              <a href="/setlists/{setlist.id}/play?at={index + 1}" class="shrink-0 rounded px-2 py-1 text-xs text-clef-stone-300 hover:text-clef-ivory" aria-label="Play from {entry.title}">▶</a>
            {/if}
            {#if setlist.can_edit}
              <div class="flex shrink-0 items-center">
                <button type="button" onclick={() => move(index, index - 1)} disabled={index === 0} class="rounded px-2 py-1 text-clef-stone-300 hover:text-clef-ivory disabled:opacity-30" aria-label="Move {entry.title} up">↑</button>
                <button type="button" onclick={() => move(index, index + 1)} disabled={index === entries.length - 1} class="rounded px-2 py-1 text-clef-stone-300 hover:text-clef-ivory disabled:opacity-30" aria-label="Move {entry.title} down">↓</button>
                <button type="button" onclick={() => remove(index)} class="rounded px-2 py-1 text-clef-stone-300/70 hover:text-clef-claret" aria-label="Remove {entry.title} from the setlist">✕</button>
              </div>
            {/if}
          </li>
        {/each}
      </ol>
    {/if}

    {#if setlist.can_edit}
      <div class="pt-4">
        <button type="button" onclick={deleteSetlist} class="text-sm text-clef-claret/80 hover:text-clef-claret">Delete setlist</button>
      </div>
    {/if}
  </div>

  <AddPiecesDialog bind:open={addOpen} onAdd={addPieces} />
{:else}
  <p class="px-6 py-10 text-sm text-clef-stone-300/70">Loading…</p>
{/if}
