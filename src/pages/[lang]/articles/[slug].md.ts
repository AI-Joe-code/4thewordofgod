import type { APIContext } from 'astro';
import { env } from 'cloudflare:workers';
import { SITE_URL } from '../../../lib/site';
import { chapterToMarkdown } from '../../../lib/markdown.js';
import type { CommentaryData } from '../../../lib/content';

// Clean-Markdown twin of an article page (`/{lang}/articles/{slug}.md`). Mirrors
// the chapter twin: one R2 read, edge-cached, advertised via the page's
// <link rel="alternate" type="text/markdown">.
export const prerender = false;

export async function GET(context: APIContext) {
  const { lang, slug } = context.params;
  if (!lang || !slug) {
    return new Response('Not found', { status: 404 });
  }
  if (!env.R2) {
    return new Response('R2 binding unavailable', { status: 500 });
  }

  const obj = await env.R2.get(`public-content/${lang}/articles/${slug}.json`);
  if (!obj) {
    return new Response('Not found', { status: 404 });
  }
  const data = (await obj.json()) as CommentaryData;

  const md = chapterToMarkdown(data, { lang, url: `${SITE_URL}/${lang}/articles/${slug}` });
  return new Response(md, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}
