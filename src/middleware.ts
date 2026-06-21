import { defineMiddleware } from 'astro:middleware';
import { SITE_URL } from './lib/site';

// Only the production host should be crawlable. Every page canonicals to it, so
// non-production hosts (*.workers.dev, previews, localhost) get X-Robots-Tag:
// noindex to keep the test deploy out of search and avoid canonical confusion.
const PROD_HOST = new URL(SITE_URL).hostname;

// Edge caching for on-demand (SSR) pages. Content is the same for every
// visitor of a given URL (the language lives in the path), so we cache the
// rendered response in the Cloudflare Cache API and serve subsequent hits
// without invoking R2/KV. The CDN holds it for s-maxage and may serve it
// stale-while-revalidate; explicit purges (scripts/purge_cache.js) handle
// content updates.
const CACHE_CONTROL = 'public, max-age=0, s-maxage=86400, stale-while-revalidate=604800';

// Injected at build time (see astro.config.mjs). Folded into the cache key so a
// new deploy uses a fresh cache namespace; stale HTML pointing at now-deleted
// hashed assets is never served after a redeploy.
declare const __BUILD_ID__: string;
const BUILD_ID = typeof __BUILD_ID__ === 'string' ? __BUILD_ID__ : 'dev';

export const onRequest = defineMiddleware(async (context, next) => {
  const { request, url } = context;
  const noindex = url.hostname !== PROD_HOST;

  // Every GET is cacheable: content is identical for every visitor of a given
  // URL (the language lives in the path, and the root now serves the stable
  // default-language home rather than redirecting by Accept-Language).
  const cacheable = request.method === 'GET';
  if (!cacheable) {
    const r = await next();
    if (noindex) r.headers.set('X-Robots-Tag', 'noindex');
    return r;
  }

  // caches.default is the global Cloudflare Cache API at runtime (as of Astro
  // v6 it is no longer exposed on Astro.locals.runtime); it may be absent in
  // some local/dev contexts. Degrade gracefully to plain rendering.
  let cache: Cache | undefined;
  try {
    cache = (globalThis as any).caches?.default;
  } catch {
    cache = undefined;
  }

  // Version the cache key by build id so a redeploy never serves stale HTML.
  const keyUrl = new URL(url.toString());
  keyUrl.searchParams.set('__v', BUILD_ID);
  const cacheKey = new Request(keyUrl.toString(), { method: 'GET' });

  if (cache) {
    try {
      const hit = await cache.match(cacheKey);
      // Cache API responses have immutable headers; Astro finalizes the
      // response (prepareResponse) and would throw on a raw hit. Return a
      // mutable copy so the headers can be adjusted downstream.
      if (hit) return new Response(hit.body, hit);
    } catch {
      // ignore cache read failures
    }
  }

  const response = await next();

  // Set before the clone below so cached copies (keyed per-host) carry it too.
  if (noindex) response.headers.set('X-Robots-Tag', 'noindex');

  if (response.status === 200) {
    response.headers.set('Cache-Control', CACHE_CONTROL);
    if (cache) {
      try {
        const toCache = response.clone();
        // Astro v6: the execution context moved from runtime.ctx to cfContext.
        const cfContext = (context.locals as any).cfContext;
        const waitUntil = cfContext?.waitUntil?.bind(cfContext);
        if (waitUntil) waitUntil(cache.put(cacheKey, toCache));
        else await cache.put(cacheKey, toCache);
      } catch {
        // ignore cache write failures
      }
    }
  }

  return response;
});
