<script lang="ts">
  import { PART_TYPES, uploadErrorMessage, uploadPart, type Part, type PartType } from '$lib/api';

  let {
    open = $bindable(false),
    arrangementId,
    onAdded
  }: { open?: boolean; arrangementId: string; onAdded: (part: Part) => void } = $props();

  let dialog: HTMLDialogElement;
  let file = $state<File | null>(null);
  let partType = $state<PartType>('Other');
  let instrument = $state('');
  let label = $state('');
  let progress = $state(0);
  let busy = $state(false);
  let error = $state<string | null>(null);

  $effect(() => {
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  });

  function reset() {
    file = null;
    partType = 'Other';
    instrument = label = '';
    progress = 0;
    error = null;
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!file) return;
    busy = true;
    error = null;
    try {
      const part = await uploadPart(arrangementId, file, {
        partType,
        instrument,
        label,
        onProgress: (fraction) => (progress = fraction)
      });
      open = false;
      reset();
      onAdded(part);
    } catch (e) {
      error = uploadErrorMessage(e);
    } finally {
      busy = false;
    }
  }
</script>

<dialog
  bind:this={dialog}
  onclose={() => {
    open = false;
    reset();
  }}
  oncancel={(e) => busy && e.preventDefault()}
  class="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-lg border border-clef-graphite-500 bg-clef-charcoal text-clef-stone-100 p-0 backdrop:bg-black/70"
>
  <form onsubmit={submit} class="p-6 space-y-4 text-sm">
    <h2 class="text-xl font-serif font-semibold">Add a part</h2>
    <p class="text-clef-stone-300/70">For example the cello part, or a piano reduction of the same piece.</p>
    <label class="block">
      <span class="text-clef-stone-300">PDF</span>
      <input
        type="file"
        accept="application/pdf,.pdf"
        required
        disabled={busy}
        onchange={(e) => (file = (e.currentTarget as HTMLInputElement).files?.[0] ?? null)}
        class="oc-field"
      />
    </label>
    <div class="grid grid-cols-2 gap-3">
      <label>
        <span class="text-clef-stone-300">Instrument</span>
        <input bind:value={instrument} placeholder="e.g. Cello" disabled={busy} class="oc-field" />
      </label>
      <label>
        <span class="text-clef-stone-300">Type</span>
        <select bind:value={partType} disabled={busy} class="oc-field">
          {#each PART_TYPES as type (type)}<option value={type}>{type}</option>{/each}
        </select>
      </label>
    </div>
    <label class="block">
      <span class="text-clef-stone-300">Label</span>
      <input bind:value={label} placeholder="Defaults to the instrument" disabled={busy} class="oc-field" />
    </label>
    {#if busy}
      <div class="h-1 rounded bg-clef-graphite-700 overflow-hidden">
        <div class="h-full bg-clef-claret transition-[width]" style="width: {progress * 100}%"></div>
      </div>
    {/if}
    {#if error}<p class="text-clef-claret">{error}</p>{/if}
    <div class="flex justify-end gap-2 pt-1">
      <button type="button" onclick={() => (open = false)} disabled={busy} class="px-4 py-2 rounded text-clef-stone-300 hover:text-clef-ivory disabled:opacity-40">Cancel</button>
      <button type="submit" disabled={busy || !file} class="px-4 py-2 rounded bg-clef-claret text-clef-ivory font-medium hover:bg-clef-claret/90 disabled:opacity-50">
        {busy ? 'Uploading…' : 'Add part'}
      </button>
    </div>
  </form>
</dialog>
