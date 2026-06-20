import { SITE_URL, DEFAULT_OG_IMAGE } from './site';

// Publisher for Article structured data — references the square logo asset
// (Google wants a real logo image, not the wide social-share image).
const PUBLISHER = {
  '@type': 'Organization',
  name: '4thewordofgod',
  logo: { '@type': 'ImageObject', url: `${SITE_URL}/logo.png` },
};

export interface SeoContext {
  /** Language code, e.g. 'en'. */
  lang: string;
  /** Absolute canonical URL of the current page. */
  canonical: string;
  /** Page title (breadcrumb leaf). */
  title: string;
  /** Book slug for chapter pages, e.g. 'daniel'. Omit for articles. */
  bookSlug?: string;
  /** Book display name, e.g. 'Daniel'. Falls back to the slug. */
  bookName?: string;
  /** The book's first chapter number (its landing page), e.g. '00'. */
  firstChapter?: string;
  /** ISO date for datePublished, when known (articles). */
  datePublished?: string;
}

type Node = Record<string, unknown>;

/**
 * A correct BreadcrumbList for the current page.
 * Chapter: Home > Book > Chapter. Article: Home > Title.
 * Replaces the pipeline-generated breadcrumb, whose `item` URLs pointed at a
 * non-existent /commentaries/{book}/{n} scheme (missing the /{lang}/ segment
 * and the zero-padded chapter), i.e. they 404'd.
 */
function buildBreadcrumb(ctx: SeoContext): Node {
  const items: Node[] = [
    { '@type': 'ListItem', position: 1, name: 'Home', item: `${SITE_URL}/${ctx.lang}` },
  ];
  let position = 2;
  if (ctx.bookSlug && ctx.firstChapter) {
    items.push({
      '@type': 'ListItem',
      position: position++,
      name: ctx.bookName ?? ctx.bookSlug,
      item: `${SITE_URL}/${ctx.lang}/${ctx.bookSlug}/${ctx.firstChapter}`,
    });
  }
  items.push({ '@type': 'ListItem', position, name: ctx.title, item: ctx.canonical });
  return { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: items };
}

/**
 * Add the fields Google needs for Article rich-result eligibility without
 * overwriting anything the content already provides. `image` is the key
 * required field that was missing across all chapters.
 */
function enrichArticle(article: Node, ctx: SeoContext): Node {
  return {
    ...article,
    image: article.image ?? DEFAULT_OG_IMAGE,
    inLanguage: article.inLanguage ?? ctx.lang,
    mainEntityOfPage: article.mainEntityOfPage ?? ctx.canonical,
    publisher: article.publisher ?? PUBLISHER,
    ...(ctx.datePublished && !article.datePublished
      ? { datePublished: ctx.datePublished }
      : {}),
  };
}

/**
 * Normalize the content's structured data at render time: drop the broken
 * BreadcrumbList(s), enrich any Article node, and append a correct breadcrumb.
 * One code path fixes every chapter/article in every language.
 */
export function normalizeStructuredData(
  raw: Node[] | undefined,
  ctx: SeoContext
): Node[] {
  const nodes = (raw ?? [])
    .filter((n) => n['@type'] !== 'BreadcrumbList')
    .map((n) => (n['@type'] === 'Article' ? enrichArticle(n, ctx) : n));
  nodes.push(buildBreadcrumb(ctx));
  return nodes;
}
