import fs from 'fs/promises';
import path from 'path';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';

// Load environment variables
const envPath = path.resolve(process.cwd(), '.env');
const parentEnvPath = path.resolve(process.cwd(), '../.env');

if (await fs.stat(envPath).catch(() => false)) {
    dotenv.config({ path: envPath });
} else if (await fs.stat(parentEnvPath).catch(() => false)) {
    dotenv.config({ path: parentEnvPath });
}

const API_KEY = process.env.GEMINI_API_KEY;
if (!API_KEY) {
    console.error('Error: GEMINI_API_KEY is not set in .env file or environment variables.');
    process.exit(1);
}

const genAI = new GoogleGenerativeAI(API_KEY);
const model = genAI.getGenerativeModel({ model: 'gemini-3-pro-preview' });

const INTRO_DIR = path.resolve(process.cwd(), '../Book Introductions');
const OUTPUT_DIR = path.resolve(process.cwd(), 'public/public-content/en');

async function generateWithRetry(prompt, retries = 5) {
    for (let i = 0; i < retries; i++) {
        try {
            return await model.generateContent(prompt);
        } catch (error) {
            if (error.message && (error.message.includes('429') || error.message.includes('Too Many Requests'))) {
                const waitTime = 10000 * Math.pow(2, i); // 10s, 20s, 40s...
                console.warn(`Rate limit hit. Retrying in ${waitTime / 1000}s...`);
                await new Promise(resolve => setTimeout(resolve, waitTime));
                continue;
            }
            throw error;
        }
    }
    throw new Error("Max retries exceeded");
}

async function processIntroduction(filename) {
    if (!filename.endsWith('.md') || filename === 'chaptertitles.md') return;

    const filePath = path.join(INTRO_DIR, filename);
    const content = await fs.readFile(filePath, 'utf-8');

    // Determine book name from filename (e.g., "amosintro.md" -> "Amos", "Isaiah.md" -> "Isaiah")
    let bookName = filename.replace('.md', '').replace('intro', '');
    // Capitalize first letter
    bookName = bookName.charAt(0).toUpperCase() + bookName.slice(1);

    console.log(`Processing introduction for ${bookName}...`);

    const prompt = `
You are an expert Theological Editor and SEO Content Strategist.
Your task is to convert the following Markdown content into a structured JSON object for a Bible Commentary application.

**Input Content (Markdown):**
${content}

**Instructions:**
1.  **Convert to HTML**: Convert the Markdown to semantic HTML.
2.  **Normalize**:
    *   Remove generic headers like "Introduction to..." if they are redundant.
    *   Ensure headers are hierarchically correct (h2, h3).
    *   Format scripture references if present (though less likely in intros).
3.  **Enrich (SEO & Schema)**:
    *   Generate a compelling **Meta Description** (150-160 chars).
    *   Extract relevant **Keywords**.
    *   Identify **Entities** (People, Places, Concepts).
    *   Create **FAQ** items if the text supports it.

**Output Format (JSON)**:
Return ONLY a valid JSON object with this structure:
{
  "book_name": "${bookName}",
  "chapter_number": "00",
  "title": "Introduction to ${bookName}",
  "content": "<p>HTML content here...</p>",
  "metaDescription": "...",
  "keywords": ["keyword1", "keyword2"],
  "entities": [
    { "@type": "Person", "name": "Amos", "description": "..." }
  ],
  "faq": [
    { "question": "...", "answer": "..." }
  ]
}
`;

    try {
        const result = await generateWithRetry(prompt);
        const response = await result.response;
        let text = response.text();

        // Clean up markdown
        text = text.replace(/^```json\s*/, '').replace(/\s*```$/, '');

        const json = JSON.parse(text);

        // Add standard fields
        json.structuredData = [
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": json.title,
                "description": json.metaDescription,
                "author": { "@type": "Person", "name": "Lewis P. Hussell" },
                "about": json.entities,
                "keywords": json.keywords.join(", ")
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    { "@type": "ListItem", "position": 1, "name": "Home", "item": "https://4thewordofgod.com/" },
                    { "@type": "ListItem", "position": 2, "name": "Commentaries", "item": "https://4thewordofgod.com/commentaries/" },
                    { "@type": "ListItem", "position": 3, "name": bookName, "item": `https://4thewordofgod.com/commentaries/${bookName.toLowerCase()}` }
                ]
            }
        ];

        if (json.faq && json.faq.length > 0) {
            json.structuredData.push({
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": json.faq.map(f => ({
                    "@type": "Question",
                    "name": f.question,
                }

async function main() {
                        try {
                            const files = await fs.readdir(INTRO_DIR);
                            for (const file of files) {
                                await processIntroduction(file);
                                // Small delay
                                await new Promise(resolve => setTimeout(resolve, 2000));
                            }
                            console.log("All introductions processed.");
                        } catch (error) {
                            console.error("Fatal error:", error);
                        }
                    }

main();
