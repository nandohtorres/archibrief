import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import "./globals.css";

// Bundled from upstream releases: builds and browsers need no font service.
// globals.css keeps the same --font-body/--font-mono/--font-serif mapping.
const plexSans = localFont({
  src: [
    { path: "./fonts/IBMPlexSans-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexSans-Medium.woff2", weight: "500", style: "normal" },
    { path: "./fonts/IBMPlexSans-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "./fonts/IBMPlexSans-Bold.woff2", weight: "700", style: "normal" },
    { path: "./fonts/IBMPlexSans-Italic.woff2", weight: "400", style: "italic" },
    { path: "./fonts/IBMPlexSans-MediumItalic.woff2", weight: "500", style: "italic" },
    { path: "./fonts/IBMPlexSans-SemiBoldItalic.woff2", weight: "600", style: "italic" },
    { path: "./fonts/IBMPlexSans-BoldItalic.woff2", weight: "700", style: "italic" },
  ],
  variable: "--font-plex-sans",
  display: "swap",
});
const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexMono-Medium.woff2", weight: "500", style: "normal" },
    { path: "./fonts/IBMPlexMono-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "./fonts/IBMPlexMono-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-plex-mono",
  display: "swap",
});
const sourceSerif = localFont({
  src: [
    { path: "./fonts/SourceSerif4Variable-Roman.ttf.woff2", weight: "200 900", style: "normal" },
    { path: "./fonts/SourceSerif4Variable-Italic.ttf.woff2", weight: "200 900", style: "italic" },
  ],
  variable: "--font-source-serif",
  display: "swap",
});

// The public domain; OG/Twitter image URLs resolve against it.
const SITE_URL = "https://archibrief.dev";
const TITLE = "ArchiBrief · A second opinion on your AWS architecture, with the receipts";
const DESCRIPTION =
  "ArchiBrief reviews your AWS Terraform and explains in plain language what's exposed, what could fail and why each fix matters, with the code and AWS guidance behind every finding.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "ArchiBrief",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "ArchiBrief: a second opinion on your AWS architecture, with the receipts.",
      },
    ],
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
      data-theme="light"
      className={`${plexSans.variable} ${plexMono.variable} ${sourceSerif.variable}`}
      suppressHydrationWarning
    >
      <body>{children}</body>
    </html>
  );
}
