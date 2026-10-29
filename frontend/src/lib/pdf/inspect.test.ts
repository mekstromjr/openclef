import { describe, expect, it } from 'vitest';
import { findKey } from './inspect';

describe('findKey', () => {
  it.each([
    ['Impromptu in G-flat major, Op. 90 No. 3', 'Gb major'],
    ['Impromptu in G flat Major', 'Gb major'],
    ['Nocturne in E♭ major', 'Eb major'],
    ['Prelude in C♯ minor', 'C# minor'],
    ['Waltz in A-flat Major', 'Ab major'],
    ['Sonata in c minor', 'C minor'],
    ['Etude in Gb major', 'Gb major'],
    ['Fantaisie in F# minor', 'F# minor'],
    ['Symphony No. 5 in C min.', 'C minor'],
    ['Concerto in D sharp minor', 'D# minor']
  ])('%s -> %s', (text, expected) => {
    expect(findKey(text)).toBe(expected);
  });

  it.each([
    ['Ode major chord progression'],
    ['The Phantom of the Opera'],
    ['Music by A. Composer'],
    ['E-sharp major is not a standard key signature']
  ])('finds nothing in %s', (text) => {
    expect(findKey(text)).toBeUndefined();
  });
});
