const fs = require('fs');
const glob = require('glob');

// --- Main Logic ---
// Adds Open Graph fields + a BreadcrumbList schema and folds the entity list into
// Article.about[]. (This script originally also asked Gemini to find + HTTP-validate
// a Wikipedia `sameAs` URL for each entity; that step was removed and the links were
// stripped from all content JSON, so no LLM / network calls remain here.)

function processFile(filePath) {
    console.log(`Enriching: ${filePath}`);

    try {
        const rawData = fs.readFileSync(filePath, 'utf8');
        const jsonData = JSON.parse(rawData);

        // 1. Open Graph
        jsonData['og:title'] = jsonData.title;
        jsonData['og:description'] = jsonData.metaDescription;
        delete jsonData.og_title;
        delete jsonData.og_description;

        // 2. Breadcrumbs
        const breadcrumbSchema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "Home",
                    "item": "https://4thewordofgod.com/"
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": "Commentaries",
                    "item": "https://4thewordofgod.com/commentaries/"
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": jsonData.book_name,
                    "item": `https://4thewordofgod.com/commentaries/${jsonData.book_name.toLowerCase().replace(/ /g, '-')}`
                },
                {
                    "@type": "ListItem",
                    "position": 4,
                    "name": `Chapter ${jsonData.chapter_number}`,
                    "item": `https://4thewordofgod.com/commentaries/${jsonData.book_name.toLowerCase().replace(/ /g, '-')}/${jsonData.chapter_number}`
                }
            ]
        };

        if (!Array.isArray(jsonData.structuredData)) {
            jsonData.structuredData = [jsonData.structuredData];
        }
        jsonData.structuredData = jsonData.structuredData.filter(item => item["@type"] !== "BreadcrumbList");
        jsonData.structuredData.push(breadcrumbSchema);

        // 3. Fold entities into Article.about[] (no external links)
        let entities = jsonData.entities || [];

        // Fallback to finding entities in Article schema
        if (entities.length === 0) {
            const article = jsonData.structuredData.find(item => item["@type"] === "Article");
            if (article && article.about) {
                entities = article.about.filter(item => item["@type"] !== "CreativeWork");
            }
        }

        if (entities.length > 0) {
            // We no longer link entities out, so drop any stray `sameAs`.
            for (const entity of entities) {
                delete entity.sameAs;
            }

            jsonData.entities = entities;

            // Update Article Schema
            const articleIndex = jsonData.structuredData.findIndex(item => item["@type"] === "Article");
            if (articleIndex !== -1) {
                const metadataItems = jsonData.structuredData[articleIndex].about.filter(item => item["@type"] === "CreativeWork");
                jsonData.structuredData[articleIndex].about = [...entities, ...metadataItems];
            }
        } else {
            console.log(`No entities found to fold for ${filePath}`);
        }

        // Save file
        fs.writeFileSync(filePath, JSON.stringify(jsonData, null, 2));
        console.log(`Success: ${filePath}`);

    } catch (error) {
        console.error(`Error processing ${filePath}:`, error);
    }
}

function main() {
    const specificFile = process.argv[2];

    if (specificFile) {
        processFile(specificFile);
    } else {
        const files = glob.sync('a_commentary_on_*/*.json');
        console.log(`Found ${files.length} files to enrich.`);
        for (const file of files) {
            processFile(file);
        }
    }
}

main();
