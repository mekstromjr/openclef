<script lang="ts">
  let { value }: { value: number | null } = $props();
</script>

{#if value}
  <span class="text-clef-gold tracking-tight" aria-label="Difficulty {value} of 5" title="Difficulty {value} of 5">
    {'★'.repeat(value)}<span class="text-clef-graphite-500">{'★'.repeat(5 - value)}</span>
  </span>
{/if}
