<script lang="ts">
  import { onMount } from 'svelte';

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

<main class="min-h-screen flex items-center justify-center px-6">
  <div class="text-center space-y-6">
    <h1 class="text-5xl font-semibold tracking-tight">OpenClef</h1>
    <p class="text-zinc-400 text-lg">Self-hosted sheet music library</p>
    <div class="text-sm font-mono text-zinc-500">
      {#if error}
        <span class="text-red-400">backend unreachable: {error}</span>
      {:else if version}
        backend version: <span class="text-zinc-300">{version}</span>
      {:else}
        connecting…
      {/if}
    </div>
  </div>
</main>
