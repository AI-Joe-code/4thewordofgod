// Generate per-language navigation manifests and write them to the MANIFEST
// KV namespace. The manifest is what the SSR routes read for navigation
// (book/chapter lists, articles, available languages) instead of listing R2
// on every request.
//
// Usage:
//   node scripts/generate_manifest.js [--lang=en] [--remote] [--dry-run]
//
// Default target is LOCAL KV (Miniflare, for dev). Pass --remote for prod.
// With no --lang, every language found in content-source/ is processed.

import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

const CONTENT_DIR = path.join(process.cwd(), 'content-source');
const KV_BINDING = 'MANIFEST';

const args = process.argv.slice(2);
const options = { lang: null, remote: false, dryRun: false };
for (const arg of args) {
  if (arg.startsWith('--lang=')) options.lang = arg.split('=')[1];
  else if (arg === '--remote') options.remote = true;
  else if (arg === '--dry-run') options.dryRun = true;
}

const slugify = (s) => s.toLowerCase().replace(/_/g, '-').replace(/\s+/g, '-');

async function isDir(p) {
  try {
    return (await fs.stat(p)).isDirectory();
  } catch {
    return false;
  }
}

async function readJsonChapters(jsonDir) {
  const chapters = [];
  let files;
  try {
    files = await fs.readdir(jsonDir);
  } catch {
    return chapters;
  }
  for (const file of files) {
    if (!file.endsWith('.json')) continue;
    try {
      const data = JSON.parse(await fs.readFile(path.join(jsonDir, file), 'utf-8'));
      const n = data.chapter_number || file.replace(/^.*_/, '').replace('.json', '');
      chapters.push({ n: String(n), title: data.title || '', date: data.date || null });
    } catch (e) {
      console.warn(`  Skipping unreadable ${file}: ${e.message}`);
    }
  }
  chapters.sort((a, b) => parseInt(a.n, 10) - parseInt(b.n, 10));
  return chapters;
}

async function buildManifest(lang) {
  const langDir = path.join(CONTENT_DIR, lang);
  const manifest = { lang, generatedAt: new Date().toISOString(), books: {}, articles: [] };

  for (const item of await fs.readdir(langDir)) {
    const itemPath = path.join(langDir, item);
    if (!(await isDir(itemPath))) continue; // skip homepage.json etc.

    if (item === 'articles') {
      for (const folder of await fs.readdir(itemPath)) {
        const articlePath = path.join(itemPath, folder);
        if (!(await isDir(articlePath))) continue;
        const chapters = await readJsonChapters(path.join(articlePath, 'json'));
        const first = chapters[0] || {};
        manifest.articles.push({
          slug: slugify(folder),
          title: first.title || folder,
          date: first.date || null,
        });
      }
      continue;
    }

    const chapters = await readJsonChapters(path.join(itemPath, 'json'));
    if (chapters.length === 0) continue;
    manifest.books[slugify(item)] = { name: item, chapters };
  }

  return manifest;
}

async function kvPut(key, value) {
  const target = options.remote ? '--remote' : '--local';
  if (options.dryRun) {
    console.log(`  [DRY RUN] kv put ${key} (${value.length} bytes) ${target}`);
    return;
  }
  const tmp = path.join(os.tmpdir(), `kv-${key.replace(/[^a-z0-9]/gi, '_')}-${Date.now()}.json`);
  await fs.writeFile(tmp, value, 'utf-8');
  try {
    await execAsync(
      `npx wrangler kv key put "${key}" --path="${tmp}" --binding=${KV_BINDING} ${target}`,
      { cwd: process.cwd() }
    );
  } finally {
    await fs.rm(tmp, { force: true });
  }
}

async function main() {
  let languages;
  if (options.lang) {
    languages = [options.lang];
  } else {
    languages = [];
    for (const entry of await fs.readdir(CONTENT_DIR)) {
      if (await isDir(path.join(CONTENT_DIR, entry))) languages.push(entry);
    }
  }
  languages.sort();

  console.log(
    `Generating manifests for: ${languages.join(', ')} -> ${options.remote ? 'PRODUCTION' : 'local'} KV`
  );

  for (const lang of languages) {
    const manifest = await buildManifest(lang);
    const bookCount = Object.keys(manifest.books).length;
    const chCount = Object.values(manifest.books).reduce((n, b) => n + b.chapters.length, 0);
    console.log(`  ${lang}: ${bookCount} books, ${chCount} chapters, ${manifest.articles.length} articles`);
    await kvPut(`manifest:${lang}`, JSON.stringify(manifest));
  }

  // Always refresh the global language list from what exists in content-source.
  const allLangs = [];
  for (const entry of await fs.readdir(CONTENT_DIR)) {
    if (await isDir(path.join(CONTENT_DIR, entry))) allLangs.push(entry);
  }
  allLangs.sort();
  await kvPut('manifest:languages', JSON.stringify(allLangs));

  console.log('Manifest generation complete.');
}

main().catch((e) => {
  console.error('Manifest generation failed:', e);
  process.exit(1);
});
