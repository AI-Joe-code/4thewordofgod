import type { APIContext } from 'astro';
import { SITE_URL } from '../lib/site';

// Dynamic robots.txt (replaces the former static public/robots.txt). Host-aware:
// the production host explicitly welcomes AI answer engines AND training
// crawlers (per product decision: maximize reach/citations for the ministry),
// while non-production hosts (*.workers.dev, beta) return Disallow: / to match
// the X-Robots-Tag: noindex the middleware already sets on previews.
export const prerender = false;

const PROD_HOST = new URL(SITE_URL).hostname;

// AI user-agents we explicitly welcome. Listing them (rather than relying only
// on `User-agent: *`) is an intentional, legible signal — and some crawlers only
// honor rules under their own named group.
const AI_BOTS = [
  // OpenAI
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  // Anthropic
  'ClaudeBot',
  'anthropic-ai',
  'Claude-User',
  'Claude-SearchBot',
  // Perplexity
  'PerplexityBot',
  'Perplexity-User',
  // Google (Gemini / AI Overviews opt-in)
  'Google-Extended',
  'GoogleOther',
  // Apple Intelligence
  'Applebot',
  'Applebot-Extended',
  // Others
  'CCBot',
  'Amazonbot',
  'Bytespider',
  'Meta-ExternalAgent',
  'cohere-ai',
  'DuckAssistBot',
  'YouBot',
];

export function GET(context: APIContext) {
  const headers = { 'Content-Type': 'text/plain; charset=utf-8' };

  // Use the real request Host header: `context.url` is normalized to the
  // configured `site` (astro.config.mjs), so it always reads as the prod host.
  // The Host header carries the actual hostname in both dev and at the edge.
  const host = (context.request.headers.get('host') ?? context.url.host).split(':')[0];
  if (host !== PROD_HOST) {
    return new Response('User-agent: *\nDisallow: /\n', { headers });
  }

  const body = `# 4thewordofgod.com — Bible commentary
# AI assistants and answer engines are welcome here.
# Every page has a clean Markdown version: append ".md" to its URL.
# LLM site index: ${SITE_URL}/llms.txt  ·  Full corpus: ${SITE_URL}/llms-full.txt

User-agent: *
Allow: /

# Explicitly welcomed AI crawlers (answer engines + model training)
${AI_BOTS.map((b) => `User-agent: ${b}`).join('\n')}
Allow: /

Sitemap: ${SITE_URL}/sitemap.xml
`;

  return new Response(body, { headers });
}
