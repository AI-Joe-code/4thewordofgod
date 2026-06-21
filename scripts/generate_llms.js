// Generate the LLM-facing index files and upload them to R2:
//   - public-content/{lang}/llms.txt       (site index; links to the .md twins)
//   - public-content/{lang}/llms-full.txt  (entire corpus as one Markdown doc)
//
// These are PRE-generated (rather than assembled live in the Worker) because a
// request that read all chapters would exceed the Workers free-tier limit of 50
// subrequests. Here in Node we read content-source/ from local disk with no such
// limit. The /llms.txt and /llms-full.txt routes then serve each as one R2 read.
//
// Usage:
//   node scripts/generate_llms.js [--lang=en] [--remote] [--dry-run]
//
// Default target is LOCAL R2 (Miniflare, for dev). Pass --remote for prod.
// Mirrors scripts/generate_manifest.js (CLI flags, content-source walk) and
// reuses scripts/upload_content.js's `wrangler r2 object put` mechanism.

import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { exec } from 'child_process';
import { promisify } from 'util';
import { chapterToMarkdown } from '../src/lib/markdown.js';

const execAsync = promisify(exec);

// Keep in sync with src/lib/site.ts (SITE_URL). Hardcoded because that module is
// TypeScript and this script runs under plain Node.
const SITE_URL = 'https://4thewordofgod.com';
const R2_BUCKET = 'bible-commentary-assets';
const CONTENT_DIR = path.join(process.cwd(), 'content-source');

const args = process.argv.slice(2);
const options = { lang: 'en', remote: false, dryRun: false };
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
      chapters.push(JSON.parse(await fs.readFile(path.join(jsonDir, file), 'utf-8')));
    } catch (e) {
      console.warn(`  Skipping unreadable ${file}: ${e.message}`);
    }
  }
  chapters.sort(
    (a, b) => parseInt(a.chapter_number || 0, 10) - parseInt(b.chapter_number || 0, 10)
  );
  return chapters;
}

// Walk content-source/{lang} into an ordered structure of books and articles,
// each carrying the full chapter data (so llms-full.txt can render bodies).
async function collectContent(lang) {
  const langDir = path.join(CONTENT_DIR, lang);
  const books = []; // { name, slug, chapters: data[] }
  const articles = []; // { slug, data }

  for (const item of (await fs.readdir(langDir)).sort()) {
    const itemPath = path.join(langDir, item);
    if (!(await isDir(itemPath))) continue; // skip homepage.json etc.

    if (item === 'articles') {
      for (const folder of (await fs.readdir(itemPath)).sort()) {
        const articlePath = path.join(itemPath, folder);
        if (!(await isDir(articlePath))) continue;
        const chapters = await readJsonChapters(path.join(articlePath, 'json'));
        if (chapters.length === 0) continue;
        articles.push({ slug: slugify(folder), data: chapters[0] });
      }
      continue;
    }

    const chapters = await readJsonChapters(path.join(itemPath, 'json'));
    if (chapters.length === 0) continue;
    books.push({ name: item, slug: slugify(item), chapters });
  }

  return { books, articles };
}

function chapterUrl(lang, bookSlug, n) {
  return `${SITE_URL}/${lang}/${bookSlug}/${n}`;
}
function articleUrl(lang, slug) {
  return `${SITE_URL}/${lang}/articles/${slug}`;
}

function chapterLabel(data) {
  const num = parseInt(data.chapter_number || 0, 10);
  const ref = Number.isFinite(num) && num > 0 ? `${data.book_name} ${num}` : `${data.book_name}`;
  return data.title ? `${ref} — ${data.title}` : ref;
}

function buildSummary(books) {
  const names = books.map((b) => b.name).join(', ');
  return (
    `In-depth, verse-by-verse Bible commentary${names ? ` covering ${names}` : ''}, ` +
    `each chapter with FAQs and Schema.org structured data, plus prophetic articles. ` +
    `Free to read and multilingual.`
  );
}

function buildIndex(lang, { books, articles }) {
  const out = [`# 4thewordofgod.com — Bible Commentary`, ``, `> ${buildSummary(books)}`, ``];

  for (const book of books) {
    out.push(`## ${book.name}`);
    for (const data of book.chapters) {
      out.push(`- [${chapterLabel(data)}](${chapterUrl(lang, book.slug, data.chapter_number)}.md)`);
    }
    out.push(``);
  }

  if (articles.length > 0) {
    out.push(`## Articles`);
    for (const a of articles) {
      out.push(`- [${a.data.title || a.slug}](${articleUrl(lang, a.slug)}.md)`);
    }
    out.push(``);
  }

  out.push(
    `## Optional`,
    `- [Full corpus in one file](${SITE_URL}/llms-full.txt)`,
    `- [Human-readable site](${SITE_URL}/${lang})`,
    ``
  );

  return out.join('\n');
}

function buildFull(lang, { books, articles }) {
  const docs = [`# 4thewordofgod.com — Bible Commentary (full text, ${lang})`, ``, `> ${buildSummary(books)}`];

  for (const book of books) {
    for (const data of book.chapters) {
      docs.push(chapterToMarkdown(data, { lang, url: chapterUrl(lang, book.slug, data.chapter_number) }));
    }
  }
  for (const a of articles) {
    docs.push(chapterToMarkdown(a.data, { lang, url: articleUrl(lang, a.slug) }));
  }

  return docs.join('\n\n');
}

async function r2Put(key, value) {
  const target = options.remote ? '--remote' : '--local';
  if (options.dryRun) {
    console.log(`  [DRY RUN] r2 put ${key} (${value.length} bytes) ${target}`);
    return;
  }
  const tmp = path.join(os.tmpdir(), `r2-${key.replace(/[^a-z0-9]/gi, '_')}-${Date.now()}.txt`);
  await fs.writeFile(tmp, value, 'utf-8');
  try {
    await execAsync(
      `npx wrangler r2 object put ${R2_BUCKET}/${key} --file="${tmp}" ${target}`,
      { cwd: process.cwd() }
    );
  } finally {
    await fs.rm(tmp, { force: true });
  }
}

async function main() {
  const lang = options.lang;
  console.log(
    `Generating llms.txt + llms-full.txt for "${lang}" -> ${options.remote ? 'PRODUCTION' : 'local'} R2`
  );

  const content = await collectContent(lang);
  const chapterCount = content.books.reduce((n, b) => n + b.chapters.length, 0);
  console.log(`  ${content.books.length} books, ${chapterCount} chapters, ${content.articles.length} articles`);

  const index = buildIndex(lang, content);
  const full = buildFull(lang, content);

  await r2Put(`public-content/${lang}/llms.txt`, index);
  await r2Put(`public-content/${lang}/llms-full.txt`, full);

  console.log(`  llms.txt: ${index.length} bytes, llms-full.txt: ${full.length} bytes`);
  console.log('LLM index generation complete.');
}

main().catch((e) => {
  console.error('LLM index generation failed:', e);
  process.exit(1);
});
