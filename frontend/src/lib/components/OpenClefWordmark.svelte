<!--
  OpenClef wordmark — the canonical typographic expression of the brand.
  "Open" in Inter SemiBold inherits text color (Ivory on dark, Charcoal
  on light); "Clef" in Crimson Pro 600 italic, always Claret. Letter-
  spacing tightened slightly to keep the seam between sans and serif
  reading as one word.

  Inherits font-size from its parent so it scales with whatever heading
  or button surrounds it. Pass `class` for sizing or layout overrides.

  Brand reference: src/routes/docs/brand/typography.md.
-->
<script lang="ts">
  let { class: className = '' }: { class?: string } = $props();
</script>

<span class="inline-flex items-baseline tracking-tight {className}">
  <span class="font-sans font-semibold">Open</span><span
    class="font-serif font-semibold italic text-clef-claret">Clef</span>
</span>
