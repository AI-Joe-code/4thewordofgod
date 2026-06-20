// Shared content types. The canonical (and only) runtime source is R2:
// chapters, articles, and the homepage are all read on-demand from R2 by the
// SSR routes. There is no build-time content import — content-source/ is only
// consumed by the offline scripts (upload_content.js / generate_manifest.js).

export interface FaqItem {
  question: string;
  answer: string;
}

export interface CommentaryData {
  book_name?: string;
  chapter_number?: string;
  title: string;
  content: string;
  metaDescription?: string;
  keywords?: string[];
  // Structured entities (Person/Place/etc.) carried in the content but not
  // rendered yet; kept loosely typed since nothing reads their fields.
  entities?: Record<string, unknown>[];
  faq?: FaqItem[];
  structuredData?: Record<string, unknown>[];
  previous_chapter?: string | null;
  next_chapter?: string | null;
  audioPath?: string;
  language?: string;
  book?: string;
  chapter?: string;
  date?: string; // Articles only
  type?: 'article' | 'commentary';
}
