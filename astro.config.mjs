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
  adapter: cloudflare({
    // Expose Cloudflare bindings (R2, etc.) to `astro dev` via Miniflare,
    // reading their config from wrangler.toml.
    platformProxy: { enabled: true },
  }),
  server: {
    allowedHosts: ['dev.4thewordofgod.com']
  }
});
