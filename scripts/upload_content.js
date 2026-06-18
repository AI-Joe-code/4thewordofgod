import fs from 'fs/promises';
import path from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';
import { parseArgs } from 'util';

const execAsync = promisify(exec);

// Parse command line arguments
const args = process.argv.slice(2);
const options = {
    lang: null,
    type: null,
    dir: null,
    dryRun: false,
    remote: false
};

args.forEach(arg => {
    if (arg.startsWith('--lang=')) options.lang = arg.split('=')[1];
    if (arg.startsWith('--type=')) options.type = arg.split('=')[1];
    if (arg.startsWith('--dir=')) options.dir = arg.split('=')[1];
    if (arg === '--dry-run') options.dryRun = true;
    if (arg === '--remote') options.remote = true;
});

if (!options.lang || !options.type || !options.dir) {
    console.error('Usage: node scripts/upload_content.js --lang=<code> --type=<json|audio|homepage> --dir=<path> [--remote] [--dry-run]');
    console.error('  Default target is the LOCAL R2 emulation (for dev). Pass --remote to upload to production R2.');
    process.exit(1);
}

const TARGET_DIR = process.cwd();

async function uploadContent() {
    try {
        console.log(`Starting upload for Language: ${options.lang}, Type: ${options.type}, Source: ${options.dir}`);

        const files = await fs.readdir(options.dir);
        const targetFiles = files.filter(file =>
            options.type === 'audio' ? file.endsWith('.mp3') : file.endsWith('.json')
        );

        console.log(`Found ${targetFiles.length} files to process.`);

        for (const file of targetFiles) {
            const localFilePath = path.join(options.dir, file);
            let r2Path;

            if (options.type === 'homepage') {
                // Language-root file (e.g. homepage.json) -> public-content/{lang}/{file}
                r2Path = `public-content/${options.lang}/${file}`;
                console.log(`Processing ${file} -> ${r2Path}`);
            } else {
                // Chapter/audio file. Expected: BookName_01.json or BookName-01.mp3
                const namePart = file.replace(/\.(json|mp3)$/, '');
                const match = namePart.match(/^(.+?)[-_](\d+)$/);

                if (!match) {
                    console.warn(`Skipping file with invalid naming format: ${file} (Expected Book_01.json or Book-01.mp3)`);
                    continue;
                }

                const bookSlug = match[1].toLowerCase().replace(/_/g, '-').replace(/\s+/g, '-');
                const chapterNum = parseInt(match[2], 10);
                console.log(`Processing ${file} -> Book: ${bookSlug}, Chapter: ${chapterNum}`);

                r2Path = `public-content/${options.lang}/${options.type}/${file}`;
            }

            // 1. Upload to R2
            if (options.dryRun) {
                console.log(`[DRY RUN] Would upload ${localFilePath} to ${r2Path}`);
            } else {
                try {
                    const targetFlag = options.remote ? '--remote' : '--local';
                    console.log(`Uploading ${file} to ${options.remote ? 'PRODUCTION' : 'local'} R2...`);
                    await execAsync(`npx wrangler r2 object put bible-commentary-assets/${r2Path} ${targetFlag} --file="${localFilePath}"`, { cwd: TARGET_DIR });
                } catch (e) {
                    console.error(`Failed to upload R2 object for ${file}:`, e.message);
                    continue;
                }
            }

            // 2. Update D1 - REMOVED
            // D1 integration has been removed.
            if (options.dryRun) {
                console.log(`[DRY RUN] D1 update skipped (removed).`);
            }
        }

        console.log('Upload process complete!');

    } catch (error) {
        console.error('Upload failed:', error);
    }
}

uploadContent();
