import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// Self-hosted at build time with size-matched fallbacks, so text doesn't
// jump when the fonts arrive and no request goes to Google at runtime.
// globals.css reads these through --font-body/--font-mono/--font-serif.
const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-plex-sans",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-mono",
  display: "swap",
});
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-source-serif",
  display: "swap",
});

// Intended public domain (archibrief.dev, registered 2026-09-08) - used
// here even though DNS isn't wired to it yet (Work-Project-Issues-Log.md,
// 2026-10-14) so OG/Twitter image URLs resolve correctly once it is,
// without needing another metadata pass at publish time.
const SITE_URL = "https://archibrief.dev";
const TITLE = "ArchiBrief · AWS architecture review";
const DESCRIPTION =
  "Typed, cited, confidence-scored review of submitted AWS Terraform architectures.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "ArchiBrief",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "ArchiBrief" }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og-image.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html
      lang="en"
      data-theme="system"
      className={`${plexSans.variable} ${plexMono.variable} ${sourceSerif.variable}`}
      suppressHydrationWarning
    >
      <body>{children}</body>
    </html>
  );
}
