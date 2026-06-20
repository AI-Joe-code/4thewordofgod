// @ts-check
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';

// https://astro.build/config
export default defineConfig({
  site: 'https://4thewordofgod.com',
  // Hybrid: routes are prerendered (static) by default. Routes that opt out
  // with `export const prerender = false` are rendered on-demand by the
  // Cloudflare adapter (Worker), reading content from R2.
  output: 'static',
  // Adapter v13 runs `astro dev` on the real workerd runtime via the Cloudflare
  // Vite plugin, reading bindings from wrangler.toml directly — the old
  // `platformProxy` option was removed.
  adapter: cloudflare(),
  server: {
    allowedHosts: ['dev.4thewordofgod.com'],
  },
  vite: {
    define: {
      // Unique per build. The middleware folds this into its edge-cache key so
      // every deploy uses a fresh cache namespace — old cached HTML (which
      // references now-deleted hashed CSS/JS) is never served after a redeploy.
      __BUILD_ID__: JSON.stringify(Date.now().toString(36)),
    },
  },
});
