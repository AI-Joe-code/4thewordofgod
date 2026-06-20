export interface Book {
  title: string;
  slug: string;
  description: string;
  /** Books whose canonical page is an article rather than a chapter list. */
  type?: 'article';
  /** Article slug under /{lang}/articles/ for article-type books. */
  articlePath?: string;
}

export const books: Book[] = [
  {
    title: 'A Commentary on Daniel',
    slug: 'daniel',
    description:
      "Echo re-echo's the views held by the King James translators, scholars of the Protestant Reformation and Reformation Period and Sir Isaac Newton.",
  },
  {
    title: 'A Commentary on Revelation',
    slug: 'revelation',
    description:
      'The old is being re-told in a new and fresh format. Like a resurrection from the dead the old truths are coming to life again.',
  },
  {
    title: 'A Commentary on Isaiah',
    slug: 'isaiah',
    description:
      'His insight into the past will illume and pierce the darkness. The scrolls of Revelation are unrolled and...',
  },
  {
    title: 'A Commentary on Amos',
    slug: 'amos',
    description: 'Explore the prophetic messages of Amos and their relevance to our times.',
  },
  {
    title: 'A Commentary on Ezra',
    slug: 'ezra',
    description: 'Detailed study of the book of Ezra and the restoration of the temple.',
  },
  {
    title: 'A Commentary on Esther',
    slug: 'esther',
    description: 'Uncover the hidden providence of God in the story of Esther.',
  },
  {
    title: 'A Commentary on Haggai',
    slug: 'haggai',
    description: 'Lessons on priorities and obedience from the prophet Haggai.',
  },
  {
    title: 'A Commentary on Nehemiah',
    slug: 'nehemiah',
    description: 'Leadership and rebuilding in the face of opposition.',
  },
  {
    title: 'Tyre - Fall of the World Trade Center',
    slug: 'tyre',
    description: 'A study on the prophecy of Tyre and its potential modern application.',
    type: 'article',
    articlePath: 'fall-of-the-world-trade-center',
  },
];

/**
 * The canonical URL for a book entry. Article-type books (e.g. Tyre) link to
 * their article page; regular commentaries link to their first chapter.
 * Centralizes the slug→href mapping that used to be duplicated across the
 * sidebar and book cards.
 */
export function bookHref(slug: string | undefined, lang: string, firstChapter = '01'): string {
  if (!slug) return '#';
  const book = books.find((b) => b.slug === slug);
  if (book?.type === 'article' && book.articlePath) {
    return `/${lang}/articles/${book.articlePath}`;
  }
  return `/${lang}/${slug}/${firstChapter}`;
}
