// Build-time content source (used to prerender articles and the sidebar nav).
// The canonical runtime source is R2; this directory is also what
// scripts/upload_content.js pushes to R2. It deliberately lives OUTSIDE
// public/ so the JSON is never copied into dist/.
//
// We import the JSON via Vite's `import.meta.glob` rather than reading it with
// `node:fs` at build time. The Cloudflare adapter (v13+) prerenders inside the
// workerd runtime, where `fs` is not available; glob is resolved by Vite at
// build time and inlined, so it works regardless of the prerender runtime.
const contentModules = import.meta.glob<CommentaryData>('../../content-source/**/json/*.json', {
  eager: true,
  import: 'default',
});

export interface CommentaryData {
  book_name?: string;
  chapter_number?: string;
  title: string;
  content: string;
  metaDescription?: string;
  keywords?: string[];
  entities?: any[];
  faq?: any[];
  structuredData?: any[];
  previous_chapter?: string | null;
  next_chapter?: string | null;
  audioPath?: string;
  language?: string; // Added to match usage
  book?: string; // Added to match usage
  chapter?: string; // Added to match usage
  date?: string; // Added for articles
  type?: 'article' | 'commentary'; // Added for articles
}

export interface CommentaryEntry {
  slug: string;
  data: CommentaryData;
}

export async function getAllCommentary(): Promise<CommentaryEntry[]> {
  const entries: CommentaryEntry[] = [];

  for (const [filePath, raw] of Object.entries(contentModules)) {
    // Glob keys look like:
    //   ../../content-source/en/Daniel/json/daniel_00.json            (commentary)
    //   ../../content-source/en/articles/Some Title/json/tyre_00.json (article)
    const marker = 'content-source/';
    const markerIndex = filePath.indexOf(marker);
    if (markerIndex === -1) continue;

    const segments = filePath.slice(markerIndex + marker.length).split('/');
    const lang = segments[0];
    // Clone: glob modules are shared/read-only, and we augment the object below.
    const data: CommentaryData = { ...raw };

    if (segments[1] === 'articles') {
      // [lang, 'articles', articleFolder, 'json', file]
      const articleFolder = segments[2];
      const articleSlug = articleFolder.toLowerCase().replace(/\s+/g, '-');

      data.language = lang;
      data.book = articleFolder; // Use folder name as "book" for now
      data.chapter = '00'; // Articles are single page
      data.type = 'article';

      entries.push({ slug: `${lang}/articles/${articleSlug}`, data });
    } else {
      // [lang, book, 'json', file]
      const book = segments[1];
      const file = segments[segments.length - 1];
      const bookSlug = book.toLowerCase();
      // Use chapter_number from data, or derive from filename (e.g. tyre_00.json -> 00)
      const chapterSlug =
        data.chapter_number || file.replace(bookSlug + '_', '').replace('.json', '');

      data.language = lang;
      data.book = data.book_name || book; // Fallback to directory name
      data.chapter = data.chapter_number || chapterSlug; // Fallback to derived slug
      data.type = 'commentary';

      entries.push({ slug: `${lang}/${bookSlug}/${chapterSlug}`, data });
    }
  }

  return entries;
}
