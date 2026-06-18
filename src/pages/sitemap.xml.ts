import type { APIContext } from 'astro';

// Sitemap index: points at one sitemap per language. Rendered on-demand so a
// newly added language appears without a rebuild. Per-language URL lists live
// in /sitemap-{lang}.xml.
export const prerender = false;

const SITE = 'https://4thewordofgod.com';

export async function GET(context: APIContext) {
  const env = (context.locals as any).runtime?.env;

  let languages: string[] = ['en'];
  try {
    const raw = await env?.MANIFEST?.get('manifest:languages');
    if (raw) languages = JSON.parse(raw);
  } catch {
    // fall back to default
  }

  let xml = '<?xml version="1.0" encoding="UTF-8"?>';
  xml += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">';
  for (const lang of languages) {
    xml += `<sitemap><loc>${SITE}/sitemap-${lang}.xml</loc></sitemap>`;
  }
  xml += '</sitemapindex>';

  return new Response(xml, { headers: { 'Content-Type': 'application/xml' } });
}
