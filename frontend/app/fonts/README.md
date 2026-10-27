# Bundled typefaces

These are unmodified WOFF2 files from the upstream release archives, under the
SIL Open Font License 1.1. Each family's original license is stored beside them.
`manifest.json` records each extracted file's SHA-256 and archive path.

- IBM Plex Sans, `@ibm/plex-sans@1.1.0`:
  https://github.com/IBM/plex/releases/tag/%40ibm/plex-sans%401.1.0
  (`ibm-plex-sans.zip`, complete WOFF2). Normal and italic 400/500/600/700.
- IBM Plex Mono, `@ibm/plex-mono@2.5.0`:
  https://github.com/IBM/plex/releases/tag/%40ibm/plex-mono%402.5.0
  (`ibm-plex-mono.zip`, complete WOFF2). Normal 400/500/600/700.
- Adobe Source Serif 4, `4.005R`:
  https://github.com/adobe-fonts/source-serif/releases/tag/4.005R
  (`source-serif-4.005_WOFF2.zip`, variable TrueType WOFF2, Roman and italic).
  The original `LICENSE.md` is from the same release tag:
  https://github.com/adobe-fonts/source-serif/blob/4.005R/LICENSE.md
  Weight range 200–900; optical sizing remains available in the font.

`app/layout.tsx` uses `next/font/local` and keeps the three existing CSS variable
names. Neither the Next build nor the resulting app needs Google Fonts.
