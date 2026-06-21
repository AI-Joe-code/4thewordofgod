// Convert the trusted commentary HTML (a small, known tag vocabulary) into clean
// Markdown for the AI-facing surfaces: the per-page `.md` twins, `/llms.txt`, and
// `/llms-full.txt`.
//
// Pure ESM with zero imports so the SAME implementation runs in two places:
//   - the Cloudflare Worker (the `.md` SSR endpoints), and
//   - the Node generator script (scripts/generate_llms.js).
// No DOM / Turndown — neither is available in the Workers runtime — so this is a
// regex serializer over the constrained tag set the pipeline emits
// (h2/h3/h4, p, strong/em, ul/li, dl/dt/dd, blockquote.primary-scripture, a, br).
// Unknown tags degrade to their text content.

/** Decode the handful of HTML entities that appear in the content. */
function decodeEntities(s) {
  return s
    .replace(/&nbsp;/g, ' ')
    .replace(/&mdash;/g, '—')
    .replace(/&ndash;/g, '–')
    .replace(/&hellip;/g, '…')
    .replace(/&rsquo;/g, '’')
    .replace(/&lsquo;/g, '‘')
    .replace(/&rdquo;/g, '”')
    .replace(/&ldquo;/g, '“')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

/** Collapse a captured inline fragment to a single trimmed line. */
function inlineText(s) {
  return (s || '').replace(/\s+/g, ' ').trim();
}

/**
 * Serialize commentary HTML to Markdown.
 * @param {string} html
 * @returns {string}
 */
export function htmlToMarkdown(html) {
  if (!html) return '';
  let s = html;

  // 1) Inline elements first (they hold no block content), so by the time the
  //    block rules run, any nested emphasis/links are already Markdown.
  s = s
    .replace(/<\s*br\s*\/?\s*>/gi, '\n')
    .replace(/<\s*(strong|b)\b[^>]*>([\s\S]*?)<\s*\/\s*\1\s*>/gi, (_m, _t, c) => `**${inlineText(c)}**`)
    .replace(/<\s*(em|i)\b[^>]*>([\s\S]*?)<\s*\/\s*\1\s*>/gi, (_m, _t, c) => `*${inlineText(c)}*`)
    .replace(/<\s*code\b[^>]*>([\s\S]*?)<\s*\/\s*code\s*>/gi, (_m, c) => `\`${inlineText(c)}\``)
    .replace(
      /<\s*a\b[^>]*\bhref\s*=\s*["']([^"']*)["'][^>]*>([\s\S]*?)<\s*\/\s*a\s*>/gi,
      (_m, href, c) => `[${inlineText(c)}](${href})`
    );

  // 2) Definition lists: pair <dt>/<dd> directly so the whitespace between them
  //    is consumed -> "- **term**: definition".
  s = s.replace(
    /<\s*dt\b[^>]*>([\s\S]*?)<\s*\/\s*dt\s*>\s*<\s*dd\b[^>]*>([\s\S]*?)<\s*\/\s*dd\s*>/gi,
    // Strip any bold already present in the term (a <dt> often wraps <strong>)
    // so the whole term is bolded once, not double-wrapped (****term****).
    (_m, t, d) => `\n- **${inlineText(t).replace(/\*\*/g, '')}**: ${inlineText(d)}`
  );

  // 3) Lists: <li> -> "- item"; the ul/ol/dl wrappers are dropped by the final
  //    tag strip (step 7).
  s = s.replace(/<\s*li\b[^>]*>([\s\S]*?)<\s*\/\s*li\s*>/gi, (_m, c) => `\n- ${inlineText(c)}`);

  // 4) Headings.
  s = s
    .replace(/<\s*h2\b[^>]*>([\s\S]*?)<\s*\/\s*h2\s*>/gi, (_m, c) => `\n\n## ${inlineText(c)}\n\n`)
    .replace(/<\s*h3\b[^>]*>([\s\S]*?)<\s*\/\s*h3\s*>/gi, (_m, c) => `\n\n### ${inlineText(c)}\n\n`)
    .replace(/<\s*h4\b[^>]*>([\s\S]*?)<\s*\/\s*h4\s*>/gi, (_m, c) => `\n\n#### ${inlineText(c)}\n\n`);

  // 5) Blockquotes (scripture) -> "> " line.
  s = s.replace(
    /<\s*blockquote\b[^>]*>([\s\S]*?)<\s*\/\s*blockquote\s*>/gi,
    (_m, c) => `\n\n> ${inlineText(c)}\n\n`
  );

  // 6) Paragraphs.
  s = s.replace(/<\s*p\b[^>]*>([\s\S]*?)<\s*\/\s*p\s*>/gi, (_m, c) => `\n\n${inlineText(c)}\n\n`);

  // 7) Strip any remaining tags, decode entities, normalize blank lines.
  s = s.replace(/<[^>]+>/g, '');
  s = decodeEntities(s);
  s = s
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  return s;
}

/**
 * Build the full Markdown document for one chapter or article.
 * @param {import('./content').CommentaryData} data
 * @param {{ lang?: string, url?: string }} [opts]
 * @returns {string}
 */
export function chapterToMarkdown(data, { lang = 'en', url = '' } = {}) {
  const lines = [`# ${inlineText(data.title)}`];

  if (data.book_name && data.chapter_number) {
    const num = parseInt(data.chapter_number, 10);
    const ref = Number.isFinite(num) && num > 0 ? `${data.book_name} ${num}` : data.book_name;
    lines.push('', `*Commentary on ${ref}*`);
  }

  if (data.metaDescription) {
    lines.push('', `> ${inlineText(data.metaDescription)}`);
  }

  const body = htmlToMarkdown(data.content || '');
  if (body) lines.push('', body);

  if (Array.isArray(data.faq) && data.faq.length > 0) {
    lines.push('', '## Frequently Asked Questions');
    for (const item of data.faq) {
      if (!item || !item.question) continue;
      lines.push('', `### ${inlineText(item.question)}`, '', inlineText(item.answer));
    }
  }

  const meta = [];
  if (url) meta.push(`Source: ${url}`);
  meta.push(`Language: ${lang}`);
  lines.push('', '---', '', `*${meta.join(' · ')}*`);

  return lines.join('\n') + '\n';
}
