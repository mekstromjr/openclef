<script lang="ts">
  import { onMount } from 'svelte';
  import OpenClefWordmark from '$lib/components/OpenClefWordmark.svelte';

  type VersionResponse = { version: string; name: string };

  let version = $state<string | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const r = await fetch('/api/v1/version');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data: VersionResponse = await r.json();
      version = data.version;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<main class="min-h-[80vh] flex items-center justify-center px-6">
  <div class="text-center space-y-6">
    <OpenClefWordmark class="text-6xl" />
    <p class="text-clef-stone-300 text-lg">Self-hosted sheet music library</p>
    <div class="text-sm font-mono text-clef-stone-300/60">
      {#if error}
        <span class="text-clef-claret">backend unreachable: {error}</span>
      {:else if version}
        backend version: <span class="text-clef-ivory">{version}</span>
      {:else}
        connecting…
      {/if}
    </div>
  </div>
</main>
