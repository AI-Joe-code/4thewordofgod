# Production deploy checklist

How this site runs in production:

- **Cloudflare Workers (Static Assets)** serves the site. The build emits
  `dist/client/` (static assets, served free from the edge) and `dist/server/`
  (the Worker). The Worker handles on-demand (SSR) routes; everything else is a
  static asset. Configured by `wrangler.toml` (`main` + `[assets]`).
  > Migrated from Cloudflare Pages → Workers when upgrading to Astro 6 /
  > `@astrojs/cloudflare` v13, which is Workers-only. Same R2/KV/runtime, same
  > free tier; only the packaging and deploy command changed.
- **R2** (`bible-commentary-assets`, binding `R2`) holds the content:
  `public-content/{lang}/json/{book}_{chapter}.json`,
  `public-content/{lang}/articles/{slug}.json`, and
  `public-content/{lang}/homepage.json`.
- **KV** (binding `MANIFEST`) holds the navigation manifests:
  `manifest:{lang}` and `manifest:languages`.
- Rendered pages are cached at the edge (`src/middleware.ts`), so most requests
  never touch R2/KV. Content updates require a cache purge.

Adding/updating content is **data only** — push to R2 + KV and purge. No rebuild
or redeploy is needed unless code changes.

---

## 0. Prerequisites

```sh
npx wrangler login        # authenticate to your Cloudflare account
npx wrangler whoami       # confirm the right account
```

---

## 1. Create the resources (one time)

```sh
# R2 bucket (skip if it already exists)
npx wrangler r2 bucket create bible-commentary-assets

# KV namespace — copy the "id" it prints
npx wrangler kv namespace create MANIFEST
```

Paste the printed id into `wrangler.toml`, replacing the placeholder. For
Workers, the id in `wrangler.toml` is authoritative at deploy time — this step
is **mandatory** before the first deploy, not optional:

```toml
[[kv_namespaces]]
binding = "MANIFEST"
id = "PASTE_REAL_ID_HERE"   # was 0000000000000000000000000000manf
```

> The adapter auto-injects a `SESSION` KV binding (sessions are unused, so it's
> harmless). If `wrangler deploy` rejects the id-less `SESSION` binding, add it
> explicitly in `wrangler.toml` pointing at the same id as `MANIFEST`:
> `[[kv_namespaces]]` / `binding = "SESSION"` / `id = "<same id>"`.

---

## 2. Bindings (one time)

The **#1 cause of "works locally, 500 in production"** is missing bindings. On
Workers these live in `wrangler.toml` and are applied automatically on
`wrangler deploy` — R2 (`R2` → `bible-commentary-assets`), KV (`MANIFEST`), the
`nodejs_compat` compatibility flag, and `compatibility_date = "2024-11-27"` are
all already declared there. Just make sure the `MANIFEST` id is real (step 1).

> If you instead connect the repo to Cloudflare for Git-based builds, set the
> same R2/KV bindings and `nodejs_compat` flag in the Worker's dashboard
> settings (Settings → Bindings / Settings → Runtime).

---

## 3. Push content to production (R2 + KV)

Run from the repo root. The `--remote` flag targets real R2/KV (without it you
write to the local dev emulation).

**PowerShell** (primary shell on this machine):

```powershell
# All book chapter JSON -> R2
Get-ChildItem content-source/en -Directory |
  Where-Object { Test-Path "$($_.FullName)/json" } |
  ForEach-Object {
    node scripts/upload_content.js --lang=en --type=json --dir="content-source/en/$($_.Name)/json" --remote
  }

# Homepage JSON -> R2
node scripts/upload_content.js --lang=en --type=homepage --dir=content-source/en --remote

# Articles -> R2 (each content-source/en/articles/<folder> -> articles/<slug>.json)
node scripts/upload_content.js --lang=en --type=article --dir=content-source/en/articles --remote

# Navigation manifest -> KV
node scripts/generate_manifest.js --lang=en --remote

# LLM index files (llms.txt + llms-full.txt) -> R2. Run after content + manifest.
node scripts/generate_llms.js --lang=en --remote
```

**Bash** (Git Bash) equivalent:

```sh
for dir in content-source/en/*/json; do
  node scripts/upload_content.js --lang=en --type=json --dir="$dir" --remote
done
node scripts/upload_content.js --lang=en --type=homepage --dir=content-source/en --remote
node scripts/upload_content.js --lang=en --type=article --dir=content-source/en/articles --remote
node scripts/generate_manifest.js --lang=en --remote
node scripts/generate_llms.js --lang=en --remote
```

Sanity-check a couple of writes:

```sh
npx wrangler r2 object get bible-commentary-assets/public-content/en/json/daniel_01.json --remote --pipe | head -c 200
npx wrangler kv key get "manifest:languages" --binding=MANIFEST --remote
```

---

## 4. Build & deploy

```sh
npm run build          # astro build -> dist/client + dist/server
npx wrangler deploy    # uploads the Worker + static assets
```

`wrangler deploy` reads `wrangler.toml` (worker name `bible-commentaries`,
`main`, `[assets]`, and all bindings). Sanity-check the artifact first with
`npx wrangler deploy --dry-run` — it should list the R2/MANIFEST/SESSION/IMAGES/
ASSETS bindings and read the asset files from `dist/client`.

> Git-connected builds are also supported: set build command `npm run build` and
> let Cloudflare run `wrangler deploy`. Ensure the dashboard bindings match
> `wrangler.toml` (see step 2).

---

## 5. Custom domain (Pages → Worker cutover)

`4thewordofgod.com` was previously served by the old **Cloudflare Pages**
project. A hostname can only belong to one service, so going live is a cutover:

1. **Detach** `4thewordofgod.com` (and `www`) from the old Pages project:
   _Workers & Pages → (old Pages project) → Custom domains → remove_.
2. **Attach** them to this Worker as custom domains — either in the dashboard
   (_Worker `bible-commentaries` → Settings → Domains & Routes → Add Custom
   Domain_) or by adding routes to `wrangler.toml` and redeploying:

   ```toml
   routes = [
     { pattern = "4thewordofgod.com", custom_domain = true },
     { pattern = "www.4thewordofgod.com", custom_domain = true },
   ]
   ```

Cloudflare provisions the DNS record + edge cert automatically. Audio stays on
`audio.4thewordofgod.com` (separate). Until the cutover, the Worker is reachable
at `bible-commentaries.<subdomain>.workers.dev` (which is `noindex` — only the
production host is crawlable).

---

## 6. Cache purge setup (one time)

Create an API token with the **Zone → Cache Purge** permission for the
`4thewordofgod.com` zone, and grab the **Zone ID** (zone overview page). Put them
in a local `.env` (already gitignored) or your shell env:

```
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_ZONE_ID=...
```

---

## 7. Verify the live site

```sh
curl -sI https://4thewordofgod.com/            # 302 -> /en
curl -s  https://4thewordofgod.com/en | head   # homepage renders
curl -sI https://4thewordofgod.com/en/daniel/01  # 200 + Cache-Control header
curl -s  https://4thewordofgod.com/sitemap.xml   # <sitemapindex>
curl -s  https://4thewordofgod.com/sitemap-en.xml | head
```

---

## Updating content later (the recurring workflow)

1. Edit/add JSON under `content-source/{lang}/...`.
2. Re-run the **step 3** commands for that language (R2 + manifest).
3. Purge the cache so changes go live before the edge TTL expires:
   ```sh
   node scripts/purge_cache.js --all
   # or target specific URLs:
   node scripts/purge_cache.js --url=https://4thewordofgod.com/en/daniel/01
   ```

No build or redeploy needed for content-only changes.

---

## Known limitations / follow-ups

- **One default OG image** (`og-default.png`) is used for every page. Per-page
  images (dynamic OG generation) would improve social-share CTR.
- **hreflang in sitemaps** (`xhtml:link`) is not emitted — on-page `<head>`
  hreflang is. Only matters at many-language scale; add before the full rollout.
- `content-source/` is the source the offline scripts push to R2; it is **no
  longer read at build time** (chapters, articles, and the homepage all render
  SSR-from-R2).
