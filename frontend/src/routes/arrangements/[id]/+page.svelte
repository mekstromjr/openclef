<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import {
    ApiError,
    MAJOR_KEYS,
    MINOR_KEYS,
    OTHER_KEYS,
    PERIODS,
    api,
    formatKey,
    type ArrangementDetail,
    type ArrangementPatch,
    type Part
  } from '$lib/api';
  import AddPartDialog from '$lib/components/library/AddPartDialog.svelte';
  import Difficulty from '$lib/components/library/Difficulty.svelte';
  import PdfViewer from '$lib/components/viewer/PdfViewer.svelte';
  import { authState } from '$lib/stores/auth.svelte';

  const id = $derived(page.params.id as string);

  let arrangement = $state<ArrangementDetail | null>(null);
  let error = $state<string | null>(null);
  let activePartId = $state<string | null>(null);
  let addPartOpen = $state(false);
  let editing = $state(false);
  let saving = $state(false);
  let saveError = $state<string | null>(null);

  // Edit form fields (strings; lists are joined for editing).
  let form = $state({
    title: '', subtitle: '', composer: '', arranger: '', instruments: '',
    key: '', period: '', difficulty: '', notes: ''
  });

  const activePart = $derived(
    arrangement?.parts.find((p) => p.id === activePartId) ?? arrangement?.parts[0] ?? null
  );
  const canDelete = $derived(
    Boolean(arrangement && authState.user && (authState.user.role === 'admin' || authState.user.id === arrangement.created_by))
  );
  const credits = $derived(
    arrangement
      ? [arrangement.composer.join(' · '), arrangement.arranger.length ? `arr. ${arrangement.arranger.join(' · ')}` : '']
          .filter(Boolean)
          .join(' — ')
      : ''
  );

  async function load(arrangementId: string) {
    try {
      arrangement = await api.get<ArrangementDetail>(`/api/v1/arrangements/${arrangementId}`);
      error = null;
      if (!arrangement.parts.some((p) => p.id === activePartId)) activePartId = arrangement.parts[0]?.id ?? null;
    } catch (e) {
      error = e instanceof ApiError && e.status === 404 ? 'This piece no longer exists.' : 'Could not load this piece.';
    }
  }

  $effect(() => {
    void load(id);
  });

  function startEditing() {
    if (!arrangement) return;
    form = {
      title: arrangement.title,
      subtitle: arrangement.subtitle ?? '',
      composer: arrangement.composer.join('; '),
      arranger: arrangement.arranger.join('; '),
      instruments: arrangement.instrumentation.join(', '),
      key: arrangement.key_signature ?? '',
      period: arrangement.period ?? '',
      difficulty: arrangement.difficulty ? String(arrangement.difficulty) : '',
      notes: arrangement.notes ?? ''
    };
    saveError = null;
    editing = true;
  }

  const split = (value: string, separator: string) =>
    value.split(separator).map((s) => s.trim()).filter(Boolean);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!arrangement) return;
    saving = true;
    saveError = null;
    const patch: ArrangementPatch = {
      title: form.title.trim(),
      subtitle: form.subtitle.trim() || null,
      // Names are "Last, First": people split on ";", instruments on ",".
      composer: split(form.composer, ';'),
      arranger: split(form.arranger, ';'),
      instrumentation: split(form.instruments, ','),
      key_signature: form.key || null,
      period: form.period || null,
      difficulty: form.difficulty ? Number(form.difficulty) : null,
      notes: form.notes.trim() || null
    };
    try {
      arrangement = await api.patch<ArrangementDetail>(`/api/v1/arrangements/${arrangement.id}`, patch);
      editing = false;
    } catch (e) {
      saveError = e instanceof ApiError && e.status === 422 ? 'Check the fields: a title is required.' : 'Saving failed. Try again.';
    } finally {
      saving = false;
    }
  }

  async function deleteArrangement() {
    if (!arrangement) return;
    if (!confirm(`Delete "${arrangement.title}" and all its parts? This can't be undone.`)) return;
    try {
      await api.delete(`/api/v1/arrangements/${arrangement.id}`);
      await goto('/');
    } catch (e) {
      saveError =
        e instanceof ApiError && e.status === 409
          ? 'This piece is on a setlist. Remove it there first.'
          : 'Deleting failed.';
    }
  }

  async function removePart(part: Part) {
    if (!arrangement || !confirm(`Remove the "${part.label}" part?`)) return;
    try {
      await api.delete(`/api/v1/arrangements/${arrangement.id}/parts/${part.id}`);
      await load(arrangement.id);
    } catch {
      saveError = 'Only the person who uploaded a part (or an admin) can remove it.';
    }
  }
</script>

<svelte:head><title>{arrangement ? `${arrangement.title} · OpenClef` : 'OpenClef'}</title></svelte:head>

{#if error}
  <div class="max-w-3xl mx-auto px-6 py-16 text-center space-y-4">
    <p class="text-clef-stone-300">{error}</p>
    <a href="/" class="text-clef-claret hover:underline">Back to the library</a>
  </div>
{:else if arrangement}
  <div class="flex flex-col h-[calc(100dvh-3.5rem)]">
    <header class="px-4 sm:px-6 pt-4 pb-3 space-y-3 border-b border-clef-graphite-500">
      <a href="/" class="text-sm text-clef-stone-300/70 hover:text-clef-ivory">← Library</a>

      {#if editing}
        <form onsubmit={save} class="grid grid-cols-1 sm:grid-cols-6 gap-3 text-sm max-w-5xl">
          <label class="sm:col-span-3"><span class="text-clef-stone-300">Title</span>
            <input bind:value={form.title} required class="oc-field" /></label>
          <label class="sm:col-span-3"><span class="text-clef-stone-300">Subtitle</span>
            <input bind:value={form.subtitle} class="oc-field" /></label>
          <label class="sm:col-span-2"><span class="text-clef-stone-300">Composer</span>
            <input bind:value={form.composer} placeholder="Last, First; separate several with ;" class="oc-field" /></label>
          <label class="sm:col-span-2"><span class="text-clef-stone-300">Arranger</span>
            <input bind:value={form.arranger} placeholder="Last, First; separate several with ;" class="oc-field" /></label>
          <label class="sm:col-span-2"><span class="text-clef-stone-300">Instruments</span>
            <input bind:value={form.instruments} placeholder="e.g. Piano, Cello" class="oc-field" /></label>
          <label class="sm:col-span-2"><span class="text-clef-stone-300">Key</span>
            <select bind:value={form.key} class="oc-field">
              <option value="">—</option>
              <optgroup label="Major">{#each MAJOR_KEYS as key (key)}<option value={key}>{formatKey(key)}</option>{/each}</optgroup>
              <optgroup label="Minor">{#each MINOR_KEYS as key (key)}<option value={key}>{formatKey(key)}</option>{/each}</optgroup>
              <optgroup label="Other">{#each OTHER_KEYS as key (key)}<option value={key}>{key}</option>{/each}</optgroup>
            </select></label>
          <label class="sm:col-span-2"><span class="text-clef-stone-300">Period</span>
            <select bind:value={form.period} class="oc-field">
              <option value="">—</option>
              {#each PERIODS as period (period)}<option value={period}>{period}</option>{/each}
            </select></label>
          <label class="sm:col-span-2"><span class="text-clef-stone-300">Difficulty</span>
            <select bind:value={form.difficulty} class="oc-field">
              <option value="">—</option>
              {#each [1, 2, 3, 4, 5] as level (level)}<option value={String(level)}>{'★'.repeat(level)}</option>{/each}
            </select></label>
          <label class="sm:col-span-6"><span class="text-clef-stone-300">Notes</span>
            <textarea bind:value={form.notes} rows="2" class="oc-field"></textarea></label>

          {#if arrangement.parts.length}
            <div class="sm:col-span-6 space-y-1">
              <span class="text-clef-stone-300">Parts</span>
              <ul class="flex flex-wrap gap-2">
                {#each arrangement.parts as part (part.id)}
                  <li class="flex items-center gap-2 rounded border border-clef-graphite-500 px-2 py-1">
                    {part.label}
                    <button type="button" onclick={() => removePart(part)} class="text-clef-stone-300/70 hover:text-clef-claret" aria-label="Remove part {part.label}">✕</button>
                  </li>
                {/each}
              </ul>
            </div>
          {/if}

          <div class="sm:col-span-6 flex flex-wrap items-center gap-2">
            <button type="submit" disabled={saving} class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" onclick={() => (editing = false)} class="px-4 py-2 rounded text-clef-stone-300 hover:text-clef-ivory">Cancel</button>
            {#if canDelete}
              <button type="button" onclick={deleteArrangement} class="ml-auto px-3 py-2 rounded text-clef-claret hover:bg-clef-claret/10">Delete piece</button>
            {/if}
          </div>
        </form>
      {:else}
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 space-y-1">
            <h1 class="font-serif text-2xl sm:text-3xl leading-tight">{arrangement.title}</h1>
            {#if arrangement.subtitle}<p class="text-clef-stone-300">{arrangement.subtitle}</p>{/if}
            {#if credits}<p class="text-sm text-clef-stone-300/80">{credits}</p>{/if}
            <div class="flex flex-wrap items-center gap-2 pt-1 text-xs">
              {#if arrangement.key_signature}<span class="px-2 py-0.5 rounded-full bg-clef-graphite-700">{formatKey(arrangement.key_signature)}</span>{/if}
              {#if arrangement.period}<span class="px-2 py-0.5 rounded-full bg-clef-graphite-700">{arrangement.period}</span>{/if}
              {#each arrangement.instrumentation as instrument (instrument)}
                <span class="px-2 py-0.5 rounded-full bg-clef-midnight text-clef-stone-100">{instrument}</span>
              {/each}
              <Difficulty value={arrangement.difficulty} />
            </div>
          </div>
          <div class="flex gap-2 text-sm">
            <button type="button" onclick={() => (addPartOpen = true)} class="px-3 py-1.5 rounded border border-clef-graphite-500 hover:border-clef-claret">Add part</button>
            <button type="button" onclick={startEditing} class="px-3 py-1.5 rounded border border-clef-graphite-500 hover:border-clef-claret">Edit</button>
          </div>
        </div>
      {/if}

      {#if saveError}<p class="text-sm text-clef-claret">{saveError}</p>{/if}

      {#if arrangement.parts.length > 1}
        <div role="tablist" aria-label="Parts" class="flex gap-1 overflow-x-auto text-sm">
          {#each arrangement.parts as part (part.id)}
            <button
              type="button"
              role="tab"
              aria-selected={part.id === activePart?.id}
              onclick={() => (activePartId = part.id)}
              class="shrink-0 px-3 py-1.5 rounded-t border-b-2 {part.id === activePart?.id
                ? 'border-clef-claret text-clef-ivory'
                : 'border-transparent text-clef-stone-300 hover:text-clef-ivory'}"
            >
              {part.label}
            </button>
          {/each}
        </div>
      {/if}
    </header>

    <section class="flex-1 min-h-[60vh]">
      {#if activePart}
        {#key activePart.id}
          <PdfViewer
            url={`/api/v1/parts/${activePart.id}/file`}
            downloadUrl={`/api/v1/parts/${activePart.id}/file?download=1`}
          />
        {/key}
      {:else}
        <div class="h-full flex flex-col items-center justify-center gap-3 text-clef-stone-300">
          <p>This piece has no parts yet.</p>
          <button type="button" onclick={() => (addPartOpen = true)} class="text-clef-claret hover:underline">Add one</button>
        </div>
      {/if}
    </section>
  </div>

  <AddPartDialog
    bind:open={addPartOpen}
    arrangementId={arrangement.id}
    onAdded={async (part) => {
      await load(id);
      activePartId = part.id;
    }}
  />
{:else}
  <p class="px-6 py-10 text-sm text-clef-stone-300/70">Loading…</p>
{/if}
