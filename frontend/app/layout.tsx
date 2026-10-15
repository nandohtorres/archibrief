import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

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
    <html lang="en" data-theme="system" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
