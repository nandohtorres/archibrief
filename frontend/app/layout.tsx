import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "ArchiBrief · AWS architecture review",
  description: "Typed, cited, confidence-scored review of submitted AWS Terraform architectures.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme="system" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
