import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy · ArchiBrief",
  description: "What ArchiBrief collects when you visit, and how long it's kept.",
};

// Exported as /privacy.html: the site is static files on S3 behind
// CloudFront, with no rewrite from /privacy to the .html file.
export default function PrivacyPage() {
  return (
    <div className="app-shell">
      <main id="main-content" className="privacy-page">
        <p>
          <Link href="/">← Back to ArchiBrief</Link>
        </p>
        <h1>Privacy</h1>

        <h2>What you can do here</h2>
        <p>
          You can open finished reviews of real public Terraform. They load from saved files, and
          there is no account or sign-up. Uploading your own Terraform and asking questions about a
          review are limited to the site owner for now, so the site doesn&apos;t collect anything
          you type.
        </p>

        <h2>What&apos;s stored in your browser</h2>
        <p>
          Your theme choice (light or dark), in local storage on your device. There are no
          analytics, ads or tracking cookies.
        </p>

        <h2>What&apos;s logged</h2>
        <p>
          The site runs on Amazon Web Services in the us-east-1 region. Requests to the ArchiBrief
          API are logged with the time, the route, the response and your IP address, to investigate
          errors and abuse. Those logs are kept for 30 days and then deleted automatically.
        </p>

        <h2>Questions</h2>
        <p>
          Open an issue on the{" "}
          <a href="https://github.com/nandohtorres/archibrief/issues">project&apos;s GitHub</a>. For
          security issues, see{" "}
          <a href="https://github.com/nandohtorres/archibrief/blob/master/SECURITY.md">
            the security policy
          </a>
          .
        </p>
      </main>
    </div>
  );
}
