import { describe, expect, it } from 'vitest';
import { moveItem, orderChanged, removeItem, startIndex, toWrite } from './order';

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
  const entry = (arrangement_id: string, part_id: string | null = null) => ({
    arrangement_id, part_id, title: 'x', position: 0
  });
  it('keeps only arrangement and part', () => {
    expect(toWrite([entry('a', 'p1')])).toEqual([{ arrangement_id: 'a', part_id: 'p1' }]);
  });
  it('detects reorders and part changes, not object identity', () => {
    const saved = [entry('a'), entry('b')];
    expect(orderChanged(saved, [entry('a'), entry('b')])).toBe(false);
    expect(orderChanged(saved, [entry('b'), entry('a')])).toBe(true);
    expect(orderChanged(saved, [entry('a', 'p2'), entry('b')])).toBe(true);
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
