import type { APIContext } from 'astro';
import { env } from 'cloudflare:workers';
import { SITE_URL } from '../../../lib/site';
import { chapterToMarkdown } from '../../../lib/markdown.js';
import type { CommentaryData } from '../../../lib/content';

// Clean-Markdown twin of a chapter page (`/{lang}/{book}/{chapter}.md`), the
// format AI answer engines prefer. One R2 read per request (well within the
// Workers free-tier 50-subrequest limit); the edge-cache middleware serves
// repeat hits. Advertised from the HTML page via <link rel="alternate"
// type="text/markdown">.
export const prerender = false;

export async function GET(context: APIContext) {
  const { lang, book, chapter } = context.params;
  if (!lang || !book || !chapter) {
    return new Response('Not found', { status: 404 });
  }
  if (!env.R2) {
    return new Response('R2 binding unavailable', { status: 500 });
  }

  const obj = await env.R2.get(`public-content/${lang}/json/${book}_${chapter}.json`);
  if (!obj) {
    return new Response('Not found', { status: 404 });
  }
  const data = (await obj.json()) as CommentaryData;

  const md = chapterToMarkdown(data, { lang, url: `${SITE_URL}/${lang}/${book}/${chapter}` });
  return new Response(md, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}
