// Centralized site-wide constants. Keep all production URLs and global
// defaults here so they are defined once and imported where needed.

export const SITE_URL = 'https://4thewordofgod.com';

// Audio files live on a dedicated subdomain; chapter/article pages build full
// URLs from the relative audioPath stored in content.
export const AUDIO_BASE = 'https://audio.4thewordofgod.com';

export const DEFAULT_LANG = 'en';

// Default social-share image. Drop a real 1200x630 PNG at public/og-default.png
// and flip HAS_OG_IMAGE to true to enable rich link previews. While false, the
// og:image / twitter:image tags are omitted (see Layout.astro) so production
// never references a missing file.
export const DEFAULT_OG_IMAGE = `${SITE_URL}/og-default.png`;
export const HAS_OG_IMAGE = false;
