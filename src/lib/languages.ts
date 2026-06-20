
export const LANGUAGES: Record<string, { code: string; direction: 'ltr' | 'rtl'; name: string }> = {
    en: { code: 'en', direction: 'ltr', name: 'English' },
    es: { code: 'es', direction: 'ltr', name: 'Spanish' },
    fr: { code: 'fr', direction: 'ltr', name: 'French' },
    de: { code: 'de', direction: 'ltr', name: 'German' },
    it: { code: 'it', direction: 'ltr', name: 'Italian' },
    pt: { code: 'pt', direction: 'ltr', name: 'Portuguese' },
    ru: { code: 'ru', direction: 'ltr', name: 'Russian' },
    zh: { code: 'zh', direction: 'ltr', name: 'Chinese' },
    ja: { code: 'ja', direction: 'ltr', name: 'Japanese' },
    ko: { code: 'ko', direction: 'ltr', name: 'Korean' },
    ar: { code: 'ar', direction: 'rtl', name: 'Arabic' },
    he: { code: 'he', direction: 'rtl', name: 'Hebrew' },
    fa: { code: 'fa', direction: 'rtl', name: 'Persian' },
    ur: { code: 'ur', direction: 'rtl', name: 'Urdu' },
};

export function getLanguageDirection(code: string): 'ltr' | 'rtl' {
    return LANGUAGES[code]?.direction || 'ltr';
}

// Minimal shape of the MANIFEST KV binding we need (avoids a hard dependency
// on the Cloudflare types in modules that just read the language list).
type ManifestKV = { get(key: string): Promise<string | null> };

/**
 * The languages the site is currently published in, sourced from the global
 * `manifest:languages` KV key (the same source the root redirect and sitemap
 * index use). Falls back to the statically-known languages when the manifest
 * has not been generated yet. Used to render hreflang alternates.
 */
export async function getAvailableLanguages(manifest: ManifestKV | undefined): Promise<string[]> {
    if (manifest) {
        try {
            const raw = await manifest.get('manifest:languages');
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed) && parsed.length > 0) return parsed as string[];
            }
        } catch {
            // fall through to the static default
        }
    }
    return Object.keys(LANGUAGES);
}
