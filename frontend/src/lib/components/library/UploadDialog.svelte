<script lang="ts">
  import {
    KEY_SIGNATURES,
    PART_TYPES,
    uploadArrangement,
    uploadErrorMessage,
    type PartType,
    type UploadMetadata
  } from '$lib/api';

  let {
    open = $bindable(false),
    knownInstruments = [],
    onUploaded
  }: {
    open?: boolean;
    knownInstruments?: string[];
    onUploaded: () => void;
  } = $props();

  type Status = 'queued' | 'uploading' | 'done' | 'failed';
  type QueuedFile = { file: File; status: Status; progress: number; error?: string };

  let dialog: HTMLDialogElement;
  let fileInput: HTMLInputElement;
  let queue = $state<QueuedFile[]>([]);
  let dragging = $state(false);
  let busy = $state(false);

  // Optional details, only offered for a single file.
  let title = $state('');
  let composer = $state('');
  let arranger = $state('');
  let instruments = $state('');
  let keySignature = $state('');
  let difficulty = $state('');
  let partType = $state<PartType>('Full Score');

  const single = $derived(queue.length === 1);
  const finished = $derived(queue.length > 0 && queue.every((q) => q.status === 'done' || q.status === 'failed'));

  $effect(() => {
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  function reset() {
    queue = [];
    title = composer = arranger = instruments = keySignature = difficulty = '';
    partType = 'Full Score';
  }

  function close() {
    if (busy) return;
    const uploadedAny = queue.some((q) => q.status === 'done');
    open = false;
    reset();
    if (uploadedAny) onUploaded();
  }

  function addFiles(files: FileList | File[]) {
    const pdfs = Array.from(files).filter(
      (f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
    );
    queue = [...queue, ...pdfs.map((file) => ({ file, status: 'queued' as Status, progress: 0 }))];
  }

  // Names are "Last, First", so people lists split on semicolons;
  // instrument names never contain commas, so those split on commas.
  function list(value: string, separator: ',' | ';'): string[] | undefined {
    const items = value.split(separator).map((s) => s.trim()).filter(Boolean);
    return items.length ? items : undefined;
  }

  function metadataForSingle(): UploadMetadata {
    const metadata: UploadMetadata = {};
    if (title.trim()) metadata.title = title.trim();
    const composers = list(composer, ';');
    const arrangers = list(arranger, ';');
    const instrumentList = list(instruments, ',');
    if (composers) metadata.composer = composers;
    if (arrangers) metadata.arranger = arrangers;
    if (instrumentList) metadata.instrumentation = instrumentList;
    if (keySignature) metadata.key_signature = keySignature;
    if (difficulty) metadata.difficulty = Number(difficulty);
    return metadata;
  }

  async function uploadAll(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    const metadata = single ? metadataForSingle() : undefined;
    for (const item of queue) {
      if (item.status === 'done') continue;
      item.status = 'uploading';
      item.error = undefined;
      try {
        await uploadArrangement(item.file, {
          metadata,
          partType,
          onProgress: (fraction) => (item.progress = fraction)
        });
        item.status = 'done';
        item.progress = 1;
      } catch (error) {
        item.status = 'failed';
        item.error = uploadErrorMessage(error);
      }
    }
    busy = false;
  }

  function formatSize(bytes: number): string {
    return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
  }
</script>

<dialog
  bind:this={dialog}
  onclose={() => (open = false)}
  oncancel={(e) => {
    if (busy) e.preventDefault();
  }}
  class="m-auto w-[min(36rem,calc(100vw-2rem))] rounded-lg border border-clef-graphite-500 bg-clef-charcoal text-clef-stone-100 p-0 backdrop:bg-black/70"
>
  <form onsubmit={uploadAll} class="p-6 space-y-5">
    <header class="flex items-start justify-between gap-4">
      <div>
        <h2 class="text-xl font-serif font-semibold">Add music</h2>
        <p class="text-sm text-clef-stone-300/70">
          One PDF per piece. Titles and composers are read from the PDF when it has them.
        </p>
      </div>
      <button type="button" onclick={close} disabled={busy} class="text-clef-stone-300 hover:text-clef-ivory disabled:opacity-40" aria-label="Close">✕</button>
    </header>

    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      ondragover={(e) => {
        e.preventDefault();
        dragging = true;
      }}
      ondragleave={() => (dragging = false)}
      ondrop={(e) => {
        e.preventDefault();
        dragging = false;
        if (e.dataTransfer?.files) addFiles(e.dataTransfer.files);
      }}
      class="rounded-lg border-2 border-dashed p-6 text-center transition-colors {dragging
        ? 'border-clef-claret bg-clef-claret/10'
        : 'border-clef-graphite-500'}"
    >
      <p class="text-sm text-clef-stone-300">Drop PDFs here, or</p>
      <button
        type="button"
        onclick={() => fileInput.click()}
        disabled={busy}
        class="mt-2 px-3 py-1.5 rounded border border-clef-graphite-500 hover:border-clef-claret text-sm"
      >
        Choose files
      </button>
      <input
        bind:this={fileInput}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        class="hidden"
        onchange={(e) => {
          const input = e.currentTarget as HTMLInputElement;
          if (input.files) addFiles(input.files);
          input.value = '';
        }}
      />
    </div>

    {#if queue.length}
      <ul class="space-y-2 max-h-48 overflow-y-auto">
        {#each queue as item, index (index)}
          <li class="text-sm">
            <div class="flex items-center justify-between gap-3">
              <span class="truncate">{item.file.name}</span>
              <span class="shrink-0 text-xs {item.status === 'failed' ? 'text-clef-claret' : 'text-clef-stone-300/70'}">
                {#if item.status === 'done'}Added{:else if item.status === 'failed'}Failed{:else if item.status === 'uploading'}{Math.round(item.progress * 100)}%{:else}{formatSize(item.file.size)}{/if}
              </span>
            </div>
            {#if item.status === 'uploading' || item.status === 'done'}
              <div class="mt-1 h-1 rounded bg-clef-graphite-700 overflow-hidden">
                <div class="h-full bg-clef-claret transition-[width]" style="width: {item.progress * 100}%"></div>
              </div>
            {/if}
            {#if item.error}
              <p class="text-xs text-clef-claret mt-0.5">{item.error}</p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#if single && !finished}
      <fieldset class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm" disabled={busy}>
        <legend class="sr-only">Details (optional)</legend>
        <label class="sm:col-span-2">
          <span class="text-clef-stone-300">Title</span>
          <input bind:value={title} placeholder="From the PDF or file name" class="field" />
        </label>
        <label>
          <span class="text-clef-stone-300">Composer</span>
          <input bind:value={composer} placeholder="Last, First; separate several with ;" class="field" />
        </label>
        <label>
          <span class="text-clef-stone-300">Arranger</span>
          <input bind:value={arranger} placeholder="Last, First; separate several with ;" class="field" />
        </label>
        <label class="sm:col-span-2">
          <span class="text-clef-stone-300">Instruments</span>
          <input bind:value={instruments} list="known-instruments" placeholder="e.g. Piano, Cello" class="field" />
          <datalist id="known-instruments">
            {#each knownInstruments as name (name)}<option value={name}></option>{/each}
          </datalist>
        </label>
        <label>
          <span class="text-clef-stone-300">Key</span>
          <select bind:value={keySignature} class="field">
            <option value="">—</option>
            {#each KEY_SIGNATURES as key (key)}<option value={key}>{key}</option>{/each}
          </select>
        </label>
        <label>
          <span class="text-clef-stone-300">Difficulty</span>
          <select bind:value={difficulty} class="field">
            <option value="">—</option>
            {#each [1, 2, 3, 4, 5] as level (level)}<option value={String(level)}>{'★'.repeat(level)}</option>{/each}
          </select>
        </label>
      </fieldset>
    {/if}

    {#if queue.length && !finished}
      <label class="block text-sm">
        <span class="text-clef-stone-300">Each file is a</span>
        <select bind:value={partType} disabled={busy} class="field">
          {#each PART_TYPES as type (type)}<option value={type}>{type}</option>{/each}
        </select>
      </label>
    {/if}

    <footer class="flex justify-end gap-2 pt-1">
      {#if finished}
        <button type="button" onclick={close} class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90">
          Done
        </button>
      {:else}
        <button type="button" onclick={close} disabled={busy} class="px-4 py-2 rounded text-clef-stone-300 hover:text-clef-ivory disabled:opacity-40">
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy || queue.length === 0}
          class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50"
        >
          {busy ? 'Uploading…' : queue.length > 1 ? `Upload ${queue.length} files` : 'Upload'}
        </button>
      {/if}
    </footer>
  </form>
</dialog>

<style>
  .field {
    margin-top: 0.25rem;
    width: 100%;
    padding: 0.5rem 0.75rem;
    border-radius: 0.25rem;
    background: var(--color-clef-graphite-700);
    border: 1px solid var(--color-clef-graphite-500);
    color: var(--color-clef-stone-100);
  }
  .field:focus {
    outline: none;
    border-color: var(--color-clef-claret);
  }
</style>
