import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy · ArchiBrief",
  description:
    "What ArchiBrief collects when you visit or submit Terraform, and how long it's kept.",
};

// Exported as /privacy.html: the site is static files on S3 behind
// CloudFront, with no rewrite from /privacy to the .html file.
// Keep in step with infra: S3 lifecycle (modules/s3/retention.tf), DynamoDB
// TTL and point-in-time recovery (modules/dynamodb), and log retention.
export default function PrivacyPage() {
  return (
    <div className="app-shell">
      <main id="main-content" className="privacy-page">
        <p>
          <Link href="/">← Back to ArchiBrief</Link>
        </p>
        <h1>Privacy</h1>
        <p>Effective 23 October 2026.</p>

        <h2>Who runs this</h2>
        <p>
          ArchiBrief is an independent project by Fernando Torres. There are no accounts, sign-ups,
          analytics, ads or tracking cookies.
        </p>

        <h2>What you send</h2>
        <p>
          When you submit a review, ArchiBrief receives your Terraform archive, the workload brief,
          any clarification answers and any questions you ask about the report. It uses them only to
          produce that review. They are processed by Amazon Web Services in the us-east-1 region,
          including Amazon Bedrock, which runs the AI model.
        </p>
        <p>
          <strong>
            Don&apos;t submit secrets, credentials, personal data or customer records.
          </strong>{" "}
          Automated checks can miss sensitive content, and findings can be wrong.
        </p>

        <h2>Bot check and limits</h2>
        <p>
          Before an upload, Cloudflare Turnstile checks that you&apos;re not a bot. Cloudflare
          processes that check under its{" "}
          <a href="https://www.cloudflare.com/turnstile-privacy-policy/">
            Turnstile privacy policy
          </a>
          . To apply the daily limits, ArchiBrief stores a keyed hash of your network address (for
          IPv6, of its /64 network), never the address itself.
        </p>

        <h2>Access to your review</h2>
        <p>
          Your browser keeps the keys to your reviews in its local storage on your device, never in
          a URL, so you can reopen them from &ldquo;Your recent reviews&rdquo; until they expire
          after 7 days. A review link contains only its ID and opens only in the browser that
          submitted it. Clearing site data or using a private window removes that access. Anyone you
          give the read key to can read the review; follow-up actions also need your original
          network. Your theme choice (light or dark) is kept in local storage too.
        </p>

        <h2>How long it&apos;s kept</h2>
        <p>
          A review stops being available seven days after it starts. Deletion after that is
          automatic but not instant, so stored copies can outlast the seven days:
        </p>
        <ul>
          <li>
            Uploaded archives, parsed input, reports and pipeline files: scheduled for deletion
            after 7 days; older stored versions after 1 more day.
          </li>
          <li>
            Review records, findings and questions: expire after 7 days. The database removes
            expired records typically within a few days, and its recovery backups keep a copy for up
            to 35 days.
          </li>
          <li>
            Operational logs and workflow history: kept 7 to 90 days, depending on the service.
          </li>
        </ul>

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
