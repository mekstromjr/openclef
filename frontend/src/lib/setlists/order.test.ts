import { describe, expect, it } from 'vitest';
import { moveItem, orderChanged, playPosition, removeItem, startIndex, toWrite } from './order';

describe('moveItem', () => {
  const list = ['a', 'b', 'c', 'd'];
  it('moves forward and back', () => {
    expect(moveItem(list, 0, 2)).toEqual(['b', 'c', 'a', 'd']);
    expect(moveItem(list, 3, 0)).toEqual(['d', 'a', 'b', 'c']);
  });
  it('clamps the target and ignores a bad source', () => {
    expect(moveItem(list, 1, 99)).toEqual(['a', 'c', 'd', 'b']);
    expect(moveItem(list, 1, -5)).toEqual(['b', 'a', 'c', 'd']);
    expect(moveItem(list, 7, 0)).toEqual(list);
  });
  it('never mutates its input', () => {
    const original = [...list];
    moveItem(list, 0, 3);
    expect(list).toEqual(original);
  });
  it('keeps repeated pieces distinct by position', () => {
    expect(moveItem(['hymn', 'trio', 'hymn'], 2, 1)).toEqual(['hymn', 'hymn', 'trio']);
  });
});

describe('removeItem', () => {
  it('removes only the one position, even with repeats', () => {
    expect(removeItem(['hymn', 'trio', 'hymn'], 2)).toEqual(['hymn', 'trio']);
  });
});

describe('toWrite / orderChanged', () => {
  const entry = (id: string | null, arrangement_id: string | null, part_id: string | null = null, available = true) => ({
    id, arrangement_id, part_id, available, title: 'x', position: 0
  });
  it('sends kept entries by id and new ones by piece', () => {
    expect(toWrite([entry('e1', 'a', 'p1'), entry(null, 'b')])).toEqual([
      { id: 'e1', part_id: 'p1' },
      { arrangement_id: 'b', part_id: null }
    ]);
  });
  it("sends an entry the viewer can't open as its id alone", () => {
    expect(toWrite([entry('e2', null, null, false)])).toEqual([{ id: 'e2' }]);
  });
  it('detects reorders, removals and part changes, not object identity', () => {
    const saved = [entry('e1', 'a'), entry('e2', null, null, false)];
    expect(orderChanged(saved, [entry('e1', 'a'), entry('e2', null, null, false)])).toBe(false);
    expect(orderChanged(saved, [entry('e2', null, null, false), entry('e1', 'a')])).toBe(true);
    expect(orderChanged(saved, [entry('e1', 'a')])).toBe(true);
    expect(orderChanged(saved, [entry('e1', 'a', 'p2'), entry('e2', null, null, false)])).toBe(true);
  });
});

describe('playPosition', () => {
  it('counts only entries the player opens', () => {
    const entries = [{ available: true }, { available: false }, { available: true }];
    expect(playPosition(entries, 0)).toBe(1);
    expect(playPosition(entries, 2)).toBe(2);
  });
});

describe('startIndex', () => {
  it('reads a 1-based position and clamps it', () => {
    expect(startIndex('2', 5)).toBe(1);
    expect(startIndex('9', 5)).toBe(4);
  });
  it('falls back to the first piece', () => {
    expect(startIndex(null, 5)).toBe(0);
    expect(startIndex('0', 5)).toBe(0);
    expect(startIndex('two', 5)).toBe(0);
    expect(startIndex('3', 0)).toBe(0);
  });
});
