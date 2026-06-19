# `scripts/` reference

Node scripts used to (a) **build** the English commentary JSON + SEO and (b) **deploy**
content to Cloudflare (R2 / KV / cache). This file consolidates what each one does, the
order they ran, and which are **current** vs **stale**.

> ⚠️ **Big caveat — paths moved.** Most *build* scripts were written against the old
> `public/public-content/{lang}/...` layout (and some against an external
> `EXTRACTED_BOOKSv6/` project). In **Phase 2** that content moved to **`content-source/`**
> (see the project's architecture notes), so `public/public-content/` **no longer exists**.
> Those scripts therefore won't run as-is — they're kept as **reference for how the
> content was built**, not as runnable tools. The *deploy* scripts were updated for
> `content-source/` and are current.

This also documents the **field contract** the translation pipeline (`pipeline/`) must
preserve: which fields are content vs SEO vs structural, and how the body HTML is shaped.

---

## 1. Chapter JSON build pipeline (English) — how each chapter was made

Original source: raw commentary extracted (in the external `EXTRACTED_BOOKSv6` project) into
`a_commentary_on_<book>/*.json` with `book_name`, `chapter_number`, a thematic `title`, raw
`content` HTML, and `slug`. From there, an LLM chain (Google Gemini) shaped and enriched it:

| Stage | Script | Model | What it produced |
|---|---|---|---|
| 1. Body structure | **`normalize_content_llm.js`** | Gemini | Canonical body HTML (see structure below): wraps verse text in `<blockquote class="primary-scripture">`, verse headers → `<h3>{Book} {Ch}:{V}</h3>`, rewrites the "Exposition" header into an SEO `<h2>`, deletes redundant intro headers, cross-refs → `<h4>Cross References</h4>` + `<ul><li><strong>Ref:</strong> Text</li></ul>`, strips leading verse numbers / `<sup>` / `<strong>` inside scripture. |
| 2. SEO + schema | **`process_commentary.js`** | Gemini | SEO `title` (thematic, **no** book/chapter), `metaDescription` (~160 char, in author's voice), `formatted_html`, `entities[]` (3–5), `faq[]` (3–5). Builds `structuredData` = `Article` (+ `FAQPage`). Backed up `original_title`/`original_content`. |
| 3. Keywords + nav | **`enhance_seo_keywords_nav.js`** | Gemini 2.5 Pro | `keywords[]` (5–8, commentary-specific), `previous_chapter`/`next_chapter` (slug-based, from sorted chapters), syncs `Article.keywords`. |
| 4. Breadcrumbs + entities | **`process_seo_enrichment.js`** | — | Adds `og:title`/`og:description`, `BreadcrumbList` schema, folds `entities[]` into `Article.about[]`. (Originally also added Wikipedia `sameAs` links to entities — that step was dropped and the links were stripped from all JSON; see §4.) |
| 5. Cleanup | **`standardize_json.js`** *(removed — see §4)* | — | Removed `og:title`/`og:description` again, ensured `metaDescription` exists. (Why the final files in `content-source/` have **no** `og:` fields.) |
| — Book intros (parallel) | **`process_introductions.js`** | Gemini | Generates the `chapter_00` book-introduction JSON from `Book Introductions/*.md`. ⚠️ **This file is broken/truncated** (an unterminated function) — needs a rewrite if intros are regenerated. |

**Net field provenance in today's `content-source/en/**/*.json`:**
`title`←(2 SEO) · `content`←(1 structure→2 format) · `metaDescription`←(2) · `keywords[]`←(3) ·
`faq[]`←(2) · `previous_chapter`/`next_chapter`←(3) · `structuredData[]` = Article (2, entities
folded in by 4) + FAQPage (2) + BreadcrumbList (4). Static identifiers: `book_name`,
`chapter_number`. The intermediate `og:*`, `slug`, `entities[]`, `original_*` fields were
dropped by later cleanup, so current files don't carry them.

**Canonical body HTML structure** (per verse): `<h3>{Book} {Ch}:{V}</h3>` →
`<blockquote class="primary-scripture">…verse…</blockquote>` → `<p>…commentary…</p>` →
`<h4>Cross References</h4>` → `<ul><li><strong>Ref:</strong> text</li></ul>`. This is the
structure the translation pipeline preserves tag-for-tag.

> Note: stages 1 and 2 both touch HTML formatting and overlapped as the approach evolved;
> the live files match `normalize_content_llm.js`'s rules, which are authoritative for body shape.

---

## 2. Current / live deploy scripts — KEEP

Updated for `content-source/` and used by the publish flow:

| Script | Purpose |
|---|---|
| **`upload_content.js`** | Upload chapter/homepage/audio JSON to **R2** (`--lang --type --dir [--remote] [--dry-run]`). Key scheme `public-content/{lang}/json/{book}_{chapter}.json`. |
| **`generate_manifest.js`** | Build per-language nav **manifests** and write to the `MANIFEST` **KV** namespace (`--lang --remote --dry-run`). Reads `content-source/`. |
| **`purge_cache.js`** | Purge the Cloudflare **edge cache** after publishing (`--all` or `--url=`). Needs `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ZONE_ID`. |

---

## 3. Homepage scripts — current concept, STALE path

Generate `content-source/en/homepage.json` (it exists today). All three still read the old
`public/public-content/en` path, so they **need a path update** before re-running:

| Script | Purpose |
|---|---|
| `generate_homepage.js` | Build `homepage.json` (commentaries + articles lists from each book's chapter_00). |
| `generate_homepage_toc.js` | Add per-book `toc[]` (chapter_number + title) to `homepage.json`. |
| `verify_homepage.js` | Debug print: commentary count + TOC lengths. |

---

## 4. Removed in cleanup (recoverable from git history)

These stale one-offs were **deleted** — their work was done and their paths were dead. Kept
here as a record of what they did:

| Script | What it did / why removed |
|---|---|
| `migrate_english.js` | Original import from external `EXTRACTED_BOOKSv6/` → R2 flat `public-content/en/{slug}.json`; dead external paths + removed D1. Superseded by `upload_content.js`. Documented the original data dictionary (slug, og:*, original_*). |
| `publish_normalized.js` | Earlier R2 uploader (local-only, old path). Superseded by `upload_content.js`. |
| `restructure_content.js` | One-off: flat `{lang}/json/` → `{lang}/{Book}/json/`. |
| `remove_root_folders.js` | One-off: deleted the old empty `{lang}/json` + `{lang}/audio` after restructure. |
| `standardize_json.js` | One-off cleanup (removed `og:*`, ensured `metaDescription`) against the old path. |
| `migrate_to_content_collections.js` | Converted JSON → Astro content collections. Abandoned approach (live route is SSR-from-R2). Its output `src/content/` was removed too. |

Also removed: **`src/content/`** (the `commentary` collection + its orphan `config.ts`) — a
markdown duplicate of `content-source/`, defined but never used by any route.

**Wikipedia `sameAs` references removed.** The entity `sameAs` links that step 4 dropped into
`Article.about[]` (and their leftover `sameAs: null` placeholders) were stripped from **every**
content JSON by **`remove_wikipedia_references.py`** (idempotent — re-running it is a no-op). The
entity objects themselves (`@type` / `name` / `description`) are kept; only the wiki links are
gone. The wiki-linking logic was also removed from `process_seo_enrichment.js`.

---

## 5. Status of the remaining scripts

- **Current / keep:** `upload_content.js`, `generate_manifest.js`, `purge_cache.js`.
- **Reference — document the build (keep):** `normalize_content_llm.js`, `process_commentary.js`,
  `enhance_seo_keywords_nav.js`, `process_seo_enrichment.js`.
- **Need a fix before reuse** (kept; concept still live): `process_introductions.js` (broken),
  the three homepage scripts (old path), `upload_audio.js` (dead path).
- **Archived:** `Completed/create_structure_all_langs.js` — scaffolded per-language dirs using
  **short BCP-47 codes** (`en`, `zh-CN`, `es`, …); relevant to the open FLORES-vs-short-code decision.
