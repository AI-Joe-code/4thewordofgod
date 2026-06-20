import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import astro from 'eslint-plugin-astro';

export default tseslint.config(
  {
    // Build output, generated type declarations (Astro/Cloudflare), offline
    // Node scripts / Python pipeline, and one-off debug files are not app
    // source we lint.
    ignores: [
      'dist/',
      '.astro/',
      '.wrangler/',
      'scripts/',
      'pipeline/',
      'content-source/',
      '**/*.d.ts',
      'debug-env.js',
    ],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs.recommended,
  {
    rules: {
      // The Cloudflare adapter exposes some runtime values as untyped locals;
      // the casts are intentional. Warn rather than error to avoid noise.
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  }
);
