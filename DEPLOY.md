# Production deploy checklist

How this site runs in production:

- **Cloudflare Pages** serves the build (`dist/`). A small `_worker.js` handles
  the on-demand (SSR) routes; everything else is static.
- **R2** (`bible-commentary-assets`, binding `R2`) holds the content:
  `public-content/{lang}/json/{book}_{chapter}.json` and
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

Paste the printed id into `wrangler.toml`, replacing the placeholder:

```toml
[[kv_namespaces]]
binding = "MANIFEST"
id = "PASTE_REAL_ID_HERE"   # was 0000000000000000000000000000manf
```

> Optional: the Cloudflare adapter logs a `SESSION` KV warning. Sessions are
> unused, so it's harmless. To silence it, add a second binding named `SESSION`
> pointing at the same id.

---

## 2. Configure the Pages project bindings (one time)

The **#1 cause of "works locally, 500 in production"** is missing bindings.
In the Cloudflare dashboard → your Pages project → **Settings → Functions**:

- **Bindings**: add R2 binding `R2` → bucket `bible-commentary-assets`, and KV
  binding `MANIFEST` → the namespace from step 1. Set them for **Production**
  (and Preview if you use it).
- **Compatibility flags**: add `nodejs_compat` (Production + Preview).
- **Compatibility date**: `2024-11-27` or later.

(For direct `wrangler pages deploy`, the values in `wrangler.toml` are used, but
setting them in the dashboard covers Git-connected builds too.)

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

# Navigation manifest -> KV
node scripts/generate_manifest.js --lang=en --remote
```

**Bash** (Git Bash) equivalent:

```sh
for dir in content-source/en/*/json; do
  node scripts/upload_content.js --lang=en --type=json --dir="$dir" --remote
done
node scripts/upload_content.js --lang=en --type=homepage --dir=content-source/en --remote
node scripts/generate_manifest.js --lang=en --remote
```

Sanity-check a couple of writes:

```sh
npx wrangler r2 object get bible-commentary-assets/public-content/en/json/daniel_01.json --remote --pipe | head -c 200
npx wrangler kv key get "manifest:languages" --binding=MANIFEST --remote
```

---

## 4. Build & deploy

```sh
npm run build
```

Then either:

- **Git-connected project** (recommended): push to the connected branch.
  Build command `npm run build`, output directory `dist`. Cloudflare builds and
  deploys automatically.
- **Direct upload**:
  ```sh
  npx wrangler pages deploy dist --project-name=bible-commentaries
  ```

---

## 5. Custom domain

In the Pages project → **Custom domains**, ensure `4thewordofgod.com` (and
`www` if used) point at this project. Audio is served separately from
`audio.4thewordofgod.com`.

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

- **Articles** (`/[lang]/articles/[slug]`) are still prerendered at build from
  `content-source/` (English only). Converting them to SSR-from-R2 (like the
  homepage) is needed before articles scale to many languages.
- **hreflang** alternates (sitemaps + page `<head>`) are not emitted yet; they
  need a cross-language index of which chapters exist per language.
- The build still reads `content-source/` for the prerendered article. Keep the
  English `content-source/` in the repo until articles move to R2.
