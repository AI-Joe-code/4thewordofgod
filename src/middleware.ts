import { defineMiddleware } from 'astro:middleware';

// Edge caching for on-demand (SSR) pages. Content is the same for every
// visitor of a given URL (the language lives in the path), so we cache the
// rendered response in the Cloudflare Cache API and serve subsequent hits
// without invoking R2/KV. The CDN holds it for s-maxage and may serve it
// stale-while-revalidate; explicit purges (scripts/purge_cache.js) handle
// content updates.
const CACHE_CONTROL = 'public, max-age=0, s-maxage=86400, stale-while-revalidate=604800';

export const onRequest = defineMiddleware(async (context, next) => {
  const { request, url } = context;
  const runtime = (context.locals as any).runtime;

  // The root path 302-redirects based on Accept-Language, so it varies per
  // visitor and must not be edge-cached by URL alone.
  const cacheable = request.method === 'GET' && url.pathname !== '/';
  if (!cacheable) return next();

  // caches.default is available at runtime on Cloudflare; may be absent in
  // some local/dev contexts. Degrade gracefully to plain rendering.
  let cache: Cache | undefined;
  try {
    cache = runtime?.caches?.default ?? (globalThis as any).caches?.default;
  } catch {
    cache = undefined;
  }

  const cacheKey = new Request(url.toString(), { method: 'GET' });

  if (cache) {
    try {
      const hit = await cache.match(cacheKey);
      if (hit) return hit;
    } catch {
      // ignore cache read failures
    }
  }

  const response = await next();

  if (response.status === 200) {
    response.headers.set('Cache-Control', CACHE_CONTROL);
    if (cache) {
      try {
        const toCache = response.clone();
        const waitUntil = runtime?.ctx?.waitUntil?.bind(runtime.ctx);
        if (waitUntil) waitUntil(cache.put(cacheKey, toCache));
        else await cache.put(cacheKey, toCache);
      } catch {
        // ignore cache write failures
      }
    }
  }

  return response;
});
