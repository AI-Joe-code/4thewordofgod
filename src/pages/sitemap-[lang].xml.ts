import type { APIContext } from 'astro';
import { env } from 'cloudflare:workers';

// Per-language sitemap, built from that language's KV manifest: homepage,
// every chapter URL, and articles. One file per language keeps each well
// under the 50,000-URL sitemap limit and scales to hundreds of languages.
export const prerender = false;

const SITE = 'https://4thewordofgod.com';

interface Manifest {
  books: Record<string, { chapters: { n: string }[] }>;
  articles?: { slug: string }[];
}

export async function GET(context: APIContext) {
  const { lang } = context.params;

  const raw = await env.MANIFEST?.get(`manifest:${lang}`);
  if (!raw) {
    return new Response('Sitemap not found', { status: 404 });
  }
  const manifest = JSON.parse(raw) as Manifest;

  const urls: string[] = [`${SITE}/${lang}`];
  for (const bookSlug in manifest.books) {
    for (const ch of manifest.books[bookSlug].chapters) {
      urls.push(`${SITE}/${lang}/${bookSlug}/${ch.n}`);
    }
  }
  for (const article of manifest.articles ?? []) {
    urls.push(`${SITE}/${lang}/articles/${article.slug}`);
  }

  let xml = '<?xml version="1.0" encoding="UTF-8"?>';
  xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">';
  for (const u of urls) {
    xml += `<url><loc>${u}</loc></url>`;
  }
  xml += '</urlset>';

  return new Response(xml, { headers: { 'Content-Type': 'application/xml' } });
}
