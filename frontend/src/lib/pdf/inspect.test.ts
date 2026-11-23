import { describe, expect, it } from 'vitest';
import { findKey, groupLines, isReadableText, suggestFromLines, type Line } from './inspect';

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

describe('findKey with German key names', () => {
  it.each([
    ['Etüde Ges-Dur', 'Gb major'],
    ['Sonate h-moll', 'B minor'],
    ['Impromptu Es-Dur', 'Eb major'],
    ['Fantasie fis-moll', 'F# minor'],
    ['Menuett B-Dur', 'Bb major'],
    ['Nocturne Des-Dur', 'Db major'],
    ['Etüde a-moll', 'A minor']
  ])('%s -> %s', (text, expected) => {
    expect(findKey(text)).toBe(expected);
  });

  it.each([['Bundesdurchschnitt'], ['Eis-Dur is not a standard key'], ['Andante']])('finds nothing in %s', (text) => {
    expect(findKey(text)).toBeUndefined();
  });
});

describe('suggestFromLines', () => {
  const line = (text: string, size: number, top: number, left: number, right: number): Line => ({
    text, size, top, left, right
  });

  it('ignores music-font symbols that are larger than the title (LilyPond engravings)', () => {
    // A Mutopia first page: the measure number and time signature are set in
    // the music font and come out as large "text" above the real title.
    const lines = [
      line('Etüde Ges-Dur', 14, 60, 230, 380),
      line('„Schwarze Tasten"', 9, 76, 255, 355),
      line('Frédéric Chopin (1810 - 1849)', 8, 92, 420, 560),
      line('Opus 10 No. 5', 8, 102, 470, 560),
      line('5.', 20, 140, 40, 60),
      line('3 4', 24, 150, 90, 100)
    ];
    const suggestions = suggestFromLines(lines, 612, 792);
    expect(suggestions.title?.value).toBe('Etüde Ges-Dur');
    expect(suggestions.composer?.value).toBe('Frédéric Chopin');
    expect(suggestions.key?.value).toBe('Gb major');
  });

  it('returns nothing for a page with no text layer', () => {
    expect(suggestFromLines([], 612, 792)).toEqual({});
  });

  it('reads an English typeset title page', () => {
    const lines = [
      line('Impromptu', 28, 72, 230, 380),
      line('in G-flat major, Op. 90 No. 3', 13, 96, 215, 400),
      line('Franz Schubert (1797-1828)', 11, 124, 400, 560)
    ];
    const suggestions = suggestFromLines(lines, 612, 792);
    expect(suggestions.title?.value).toBe('Impromptu');
    expect(suggestions.composer?.value).toBe('Franz Schubert');
    expect(suggestions.key?.value).toBe('Gb major');
  });
});

describe('isReadableText', () => {
  it.each([['Clair de Lune'], ['Op. 10'], ['J.S. Bach'], ['Andante très expressif']])('keeps %s', (text) => {
    expect(isReadableText(text)).toBe(true);
  });
  it.each([['\u0000\u0001'], ['2\u0000'], ['PP'], ['pp'], ['mf'], ['sfz'], ['P'], [' '], ['\uE050']])('drops %j', (text) => {
    expect(isReadableText(text)).toBe(false);
  });
});

describe('suggestFromLines title placement', () => {
  it('prefers a centred title over a larger left-margin instrument label', () => {
    const lines: Line[] = [
      { text: 'SONATA IV.', size: 12, top: 50, left: 260, right: 352 },
      { text: 'Cembalo.', size: 14, top: 120, left: 20, right: 70 },
      { text: 'J.S. Bach', size: 9, top: 70, left: 470, right: 560 }
    ];
    const suggestions = suggestFromLines(lines, 612, 792);
    expect(suggestions.title?.value).toBe('SONATA IV.');
    expect(suggestions.composer?.value).toBe('J.S. Bach');
  });
});

describe('groupLines', () => {
  it('keeps a left-margin lyricist and a right-aligned composer apart', () => {
    const pieces: Line[] = [
      // The composer's baseline sits a fraction of a point higher than the lyricist's.
      { text: 'Franz Schubert', size: 15, top: 129.6, left: 423, right: 549 },
      { text: 'Johann Wolfgang von Goethe', size: 11, top: 130.2, left: 42, right: 207 },
      { text: 'Heidenröslein', size: 21, top: 96, left: 230, right: 382 }
    ];
    const lines = groupLines(pieces);
    expect(lines.map((l) => l.text).sort()).toEqual(['Franz Schubert', 'Heidenröslein', 'Johann Wolfgang von Goethe']);
    expect(suggestFromLines(lines, 612, 792).composer?.value).toBe('Franz Schubert');
  });

  it('joins words of one line, in reading order', () => {
    const pieces: Line[] = [
      { text: 'Lune', size: 14, top: 60, left: 330, right: 370 },
      { text: 'Clair de', size: 14, top: 60, left: 260, right: 324 }
    ];
    expect(groupLines(pieces).map((l) => l.text)).toEqual(['Clair de Lune']);
  });
});

describe('suggestFromLines ignores rows of dynamics', () => {
  it('does not take "P PP P" as the title', () => {
    const lines: Line[] = [
      { text: 'Suite Bergamasque – Clair de Lune', size: 14, top: 40, left: 210, right: 400 },
      { text: 'P PP P P P P', size: 18, top: 200, left: 230, right: 380 }
    ];
    expect(suggestFromLines(lines, 612, 792).title?.value).toBe('Suite Bergamasque – Clair de Lune');
  });
});
