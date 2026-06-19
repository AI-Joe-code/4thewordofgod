// Purge the Cloudflare edge cache after publishing content. The SSR pages are
// cached at the edge (see src/middleware.ts) with a long s-maxage, so updates
// only go live promptly if the affected URLs are purged.
//
// Requires env vars (a .env file works — dotenv is loaded):
//   CLOUDFLARE_API_TOKEN  (token with the "Cache Purge" permission for the zone)
//   CLOUDFLARE_ZONE_ID    (the zone id for 4thewordofgod.com)
//
// Usage:
//   node scripts/purge_cache.js --all                 # purge everything
//   node scripts/purge_cache.js --url=https://4thewordofgod.com/en/daniel/01 [--url=...]
//
// NOTE: not exercised in dev (needs real Cloudflare credentials + zone).

import 'dotenv/config';

const TOKEN = process.env.CLOUDFLARE_API_TOKEN;
const ZONE = process.env.CLOUDFLARE_ZONE_ID;

const args = process.argv.slice(2);
const urls = args.filter((a) => a.startsWith('--url=')).map((a) => a.split('=')[1]);
const purgeAll = args.includes('--all') || urls.length === 0;

if (!TOKEN || !ZONE) {
  console.error('Missing CLOUDFLARE_API_TOKEN and/or CLOUDFLARE_ZONE_ID.');
  process.exit(1);
}

const body = purgeAll ? { purge_everything: true } : { files: urls };

const res = await fetch(`https://api.cloudflare.com/client/v4/zones/${ZONE}/purge_cache`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${TOKEN}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(body),
});

const data = await res.json().catch(() => ({}));

if (!res.ok || !data.success) {
  console.error('Purge failed:', JSON.stringify(data.errors || data, null, 2));
  process.exit(1);
}

console.log(`Cache purged: ${purgeAll ? 'everything' : `${urls.length} URL(s)`}.`);
