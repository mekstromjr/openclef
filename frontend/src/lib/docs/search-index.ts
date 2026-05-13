/**
 * In-app docs search index.
 *
 * Built at module load time from every `+page.md` under `src/routes/docs`.
 * Vite's `import.meta.glob` with `?raw` inlines the markdown source into
 * the bundle — no separate prebuild step. MiniSearch indexes title +
 * description + headings + body with field boosts.
 *
 * Ticket 0153 — keep in step with the docs route tree.
 */
import MiniSearch from 'minisearch';

const modules = import.meta.glob<string>('../../routes/docs/**/+page.md', {
  eager: true,
  query: '?raw',
  import: 'default'
});

export type DocEntry = {
  id: string;
  title: string;
  description: string;
  headings: string;
  body: string;
};

function parseFrontmatter(raw: string): {
  meta: Record<string, string>;
  body: string;
} {
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return { meta: {}, body: raw };
  const meta: Record<string, string> = {};
  for (const line of match[1].split('\n')) {
    const m = line.match(/^(\w+):\s*(.*)$/);
    if (m) meta[m[1]] = m[2].trim().replace(/^['"]|['"]$/g, '');
  }
  return { meta, body: match[2] };
}

function extractHeadings(md: string): string {
  return md
    .split('\n')
    .filter((l) => /^#{2,4}\s+/.test(l))
    .map((l) => l.replace(/^#+\s+/, '').trim())
    .join(' • ');
}

function stripMarkdown(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/^#+\s+/gm, '')
    .replace(/[*_>|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function pathToSlug(path: string): string {
  // '../../routes/docs/brand/typography/+page.md' → '/docs/brand/typography'
  // '../../routes/docs/+page.md'                  → '/docs'
  const after = path.replace(/^.*?\/routes/, '').replace(/\/\+page\.md$/, '');
  return after === '' ? '/' : after;
}

export const docs: DocEntry[] = Object.entries(modules).map(([path, raw]) => {
  const { meta, body } = parseFrontmatter(raw);
  return {
    id: pathToSlug(path),
    title: meta.title ?? 'Untitled',
    description: meta.description ?? '',
    headings: extractHeadings(body),
    body: stripMarkdown(body)
  };
});

const search = new MiniSearch<DocEntry>({
  idField: 'id',
  fields: ['title', 'description', 'headings', 'body'],
  storeFields: ['title', 'description', 'id'],
  searchOptions: {
    boost: { title: 3, description: 2, headings: 2 },
    prefix: true,
    fuzzy: 0.2
  }
});

search.addAll(docs);

export type SearchHit = {
  id: string;
  title: string;
  description?: string;
  score: number;
};

export function searchDocs(query: string, limit = 8): SearchHit[] {
  const q = query.trim();
  if (q.length === 0) return [];
  return search.search(q).slice(0, limit) as unknown as SearchHit[];
}
