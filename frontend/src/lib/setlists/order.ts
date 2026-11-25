/**
 * Pure helpers for editing a setlist's running order. The editor works on a
 * local copy and saves the whole order at once, so these never mutate.
 */
import type { SetlistEntry, SetlistItemKeep, SetlistItemWrite } from '$lib/api';

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

/**
 * An entry in the editor: one loaded from the server (with its id), or a
 * piece added here and not saved yet (id null).
 */
export type EditableEntry = Omit<SetlistEntry, 'id'> & { id: string | null };

type Written = Pick<EditableEntry, 'id' | 'available' | 'arrangement_id' | 'part_id'>;

/**
 * The `entries` body for PUT /setlists/{id}/items. Existing entries go back
 * by id: one this viewer can't open goes back as the id alone, so it stays
 * exactly as it was; a visible one also sends its part. New pieces go by
 * arrangement.
 */
export function toWrite(entries: readonly Written[]): (SetlistItemKeep | SetlistItemWrite)[] {
  return entries.map(({ id, available, arrangement_id, part_id }) => {
    if (id === null) return { arrangement_id: arrangement_id as string, part_id };
    return available ? { id, part_id } : { id };
  });
}

/** True when the local order differs from what was loaded (drives "Save"). */
export function orderChanged(saved: readonly Written[], local: readonly Written[]): boolean {
  return JSON.stringify(toWrite(saved)) !== JSON.stringify(toWrite(local));
}

/** The 1-based `?at=` for the player, which skips entries that can't be opened. */
export function playPosition(entries: readonly Pick<EditableEntry, 'available'>[], index: number): number {
  return entries.slice(0, index).filter((entry) => entry.available).length + 1;
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
