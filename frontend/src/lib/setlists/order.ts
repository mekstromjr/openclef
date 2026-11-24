/**
 * Pure helpers for editing a setlist's running order. The editor works on a
 * local copy and saves the whole order at once, so these never mutate.
 */
import type { SetlistEntry, SetlistItemWrite } from '$lib/api';

/** Move the item at `from` to index `to` (clamped), returning a new array. */
export function moveItem<T>(items: readonly T[], from: number, to: number): T[] {
  if (from < 0 || from >= items.length) return [...items];
  const target = Math.min(Math.max(0, to), items.length - 1);
  if (target === from) return [...items];
  const copy = [...items];
  const [moved] = copy.splice(from, 1);
  copy.splice(target, 0, moved);
  return copy;
}

export function removeItem<T>(items: readonly T[], index: number): T[] {
  return items.filter((_, i) => i !== index);
}

/** The body for PUT /setlists/{id}/items: only what the server stores. */
export function toWrite(entries: readonly Pick<SetlistEntry, 'arrangement_id' | 'part_id'>[]): SetlistItemWrite[] {
  return entries.map(({ arrangement_id, part_id }) => ({ arrangement_id, part_id }));
}

/** True when the local order differs from what was loaded (drives "Save"). */
export function orderChanged(
  saved: readonly Pick<SetlistEntry, 'arrangement_id' | 'part_id'>[],
  local: readonly Pick<SetlistEntry, 'arrangement_id' | 'part_id'>[]
): boolean {
  return JSON.stringify(toWrite(saved)) !== JSON.stringify(toWrite(local));
}

/**
 * Index to open in the player from a `?at=` value: a 1-based position,
 * clamped into range; anything unreadable starts at the first piece.
 */
export function startIndex(at: string | null, length: number): number {
  const number = Number(at);
  if (!length || !Number.isInteger(number) || number < 1) return 0;
  return Math.min(number, length) - 1;
}
