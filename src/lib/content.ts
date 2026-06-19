import fs from 'node:fs/promises';
import path from 'node:path';

// Build-time content source (used to prerender the homepage, articles and
// sitemap). The canonical runtime source is R2; this directory is also what
// scripts/upload_content.js pushes to R2. It deliberately lives OUTSIDE
// public/ so the JSON is never copied into dist/.
const CONTENT_DIR = path.join(process.cwd(), 'content-source');

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
    book?: string;     // Added to match usage
    chapter?: string;  // Added to match usage
    date?: string;     // Added for articles
    type?: 'article' | 'commentary'; // Added for articles
}

export interface CommentaryEntry {
    slug: string;
    data: CommentaryData;
}

export async function getAllCommentary(): Promise<CommentaryEntry[]> {
    const entries: CommentaryEntry[] = [];

    try {
        const languages = await fs.readdir(CONTENT_DIR);

        for (const lang of languages) {
            const langPath = path.join(CONTENT_DIR, lang);
            const langStat = await fs.stat(langPath);
            if (!langStat.isDirectory()) continue;

            const items = await fs.readdir(langPath);

            for (const item of items) {
                const itemPath = path.join(langPath, item);
                const itemStat = await fs.stat(itemPath);
                if (!itemStat.isDirectory()) continue;

                // Check if it's the "articles" directory
                if (item === 'articles') {
                    const articles = await fs.readdir(itemPath);
                    for (const articleFolder of articles) {
                        const articlePath = path.join(itemPath, articleFolder);
                        const articleStat = await fs.stat(articlePath);
                        if (!articleStat.isDirectory()) continue;

                        const jsonDir = path.join(articlePath, 'json');
                        try {
                            const jsonFiles = await fs.readdir(jsonDir);
                            for (const file of jsonFiles) {
                                if (!file.endsWith('.json')) continue;

                                const filePath = path.join(jsonDir, file);
                                const fileContent = await fs.readFile(filePath, 'utf-8');
                                const data = JSON.parse(fileContent) as CommentaryData;

                                // Slug for articles: lang/articles/article-slug
                                // We can use the folder name as the slug, slugified
                                const articleSlug = articleFolder.toLowerCase().replace(/\s+/g, '-');
                                const slug = `${lang}/articles/${articleSlug}`;

                                data.language = lang;
                                data.book = articleFolder; // Use folder name as "book" for now
                                data.chapter = "00"; // Articles are single page
                                data.type = 'article';

                                entries.push({
                                    slug,
                                    data
                                });
                            }
                        } catch (e) {
                            continue;
                        }
                    }
                    continue; // Skip processing "articles" as a book
                }

                // Process as a Book (Commentary)
                const book = item;
                const bookPath = itemPath;

                const jsonDir = path.join(bookPath, 'json');
                try {
                    const jsonFiles = await fs.readdir(jsonDir);

                    for (const file of jsonFiles) {
                        if (!file.endsWith('.json')) continue;

                        const filePath = path.join(jsonDir, file);
                        const fileContent = await fs.readFile(filePath, 'utf-8');
                        const data = JSON.parse(fileContent) as CommentaryData;

                        // Construct slug: lang/book/chapter
                        const bookSlug = book.toLowerCase();
                        // Use chapter_number from data, or derive from filename (e.g. tyre_00.json -> 00)
                        const chapterSlug = data.chapter_number || file.replace(bookSlug + '_', '').replace('.json', '');
                        const slug = `${lang}/${bookSlug}/${chapterSlug}`;

                        // Augment data with fields expected by the page
                        data.language = lang;
                        data.book = data.book_name || book; // Fallback to directory name
                        data.chapter = data.chapter_number || chapterSlug; // Fallback to derived slug
                        data.type = 'commentary';

                        entries.push({
                            slug,
                            data
                        });
                    }
                } catch (e) {
                    // json dir might not exist or be empty
                    continue;
                }
            }
        }
    } catch (e) {
        console.error("Error reading content directory:", e);
    }

    return entries;
}
