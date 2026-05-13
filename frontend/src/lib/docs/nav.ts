/**
 * Sidebar nav for the in-app docs (ticket 0153).
 *
 * Hand-maintained for now — keep it terse. When more guides/reference
 * content lands, consider auto-deriving from the route tree, but at
 * current scale the explicit list is the source of truth and is easier
 * to reorder than a glob.
 */
export type DocNavLink = { label: string; href: string };
export type DocNavSection = { label: string; links: DocNavLink[] };

export const docsNav: DocNavSection[] = [
  {
    label: 'Brand',
    links: [
      { label: 'Overview', href: '/docs/brand' },
      { label: 'Logo & iconography', href: '/docs/brand/logo' },
      { label: 'Typography', href: '/docs/brand/typography' },
      { label: 'Color', href: '/docs/brand/color' },
      { label: 'Imagery', href: '/docs/brand/imagery' },
      { label: 'Voice & tone', href: '/docs/brand/voice' },
      { label: 'Naming', href: '/docs/brand/naming' },
      { label: 'Press kit', href: '/docs/brand/press-kit' }
    ]
  },
  {
    label: 'Guides',
    links: [{ label: 'Overview', href: '/docs/guides' }]
  },
  {
    label: 'Reference',
    links: [{ label: 'Overview', href: '/docs/reference' }]
  }
];
