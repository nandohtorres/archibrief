"use client";

import { useEffect, useRef } from "react";

// Landing content: the "master" design Fernando chose on 2026-10-15
// (frontend/design/landing-options/option-master.html), combining option A's
// editorial hero, option B's sample cards and option C's check marks,
// numbered walkthrough and checks list. Split in two so the submission form
// sits where the story turns into the product: LandingIntro (hero, samples,
// how it works) above the form, LandingClosing (what it checks, limits)
// below it.

interface LandingIntroProps {
  sampleLoading: boolean;
  onOpenSample: () => void;
}

interface SampleCard {
  title: string;
  description: string;
  stack: string;
  ready: boolean;
  icon: "card" | "play" | "cart";
}

// Only the payments sample exists today (GET /demo). The others are
// planned samples and say so.
const samples: SampleCard[] = [
  {
    title: "Payments API",
    description:
      "A customer-facing payments service: an audit-log bucket, a Lambda with an over-broad role, and a single-AZ database.",
    stack: "S3 · Lambda · IAM · RDS · KMS",
    ready: true,
    icon: "card",
  },
  {
    title: "Video streaming platform",
    description:
      "Netflix-style: CDN-fronted media origins, a transcoding pipeline, and per-viewer watch history.",
    stack: "CloudFront · S3 · Lambda · MediaConvert · DynamoDB",
    ready: false,
    icon: "play",
  },
  {
    title: "Online marketplace",
    description:
      "eBay-style: listings and search, bidding, and a payments boundary with audit retention.",
    stack: "ALB · ECS · RDS · OpenSearch · SQS",
    ready: false,
    icon: "cart",
  },
];

function SampleIcon({ icon }: { icon: SampleCard["icon"] }) {
  if (icon === "play") {
    return (
      <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
        <rect
          x="2"
          y="4"
          width="16"
          height="12"
          rx="2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
        />
        <path d="M8.5 7.5v5l4-2.5z" fill="currentColor" />
      </svg>
    );
  }
  if (icon === "cart") {
    return (
      <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M3 4h2l2 9h8l2-6H6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle cx="8" cy="16" r="1.3" fill="currentColor" />
        <circle cx="14" cy="16" r="1.3" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
      <rect
        x="2.5"
        y="5"
        width="15"
        height="10"
        rx="2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path d="M2.5 8.5h15" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

// Walkthrough steps fade in, and the connecting line fills, as they scroll
// into view. Off for reduced motion or without IntersectionObserver, and
// the steps are visible by default, so nothing depends on this running.
function useWalkthroughReveal() {
  const flowRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const flow = flowRef.current;
    const progress = progressRef.current;
    if (!flow || !progress) return;
    const steps = Array.from(flow.querySelectorAll<HTMLElement>(".landing-step"));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) {
      steps.forEach((step) => step.classList.add("is-on"));
      return;
    }
    flow.classList.add("reveal-ready");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-on");
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -20% 0px" },
    );
    steps.forEach((step) => observer.observe(step));

    const fill = () => {
      const rect = flow.getBoundingClientRect();
      const seen = Math.min(Math.max(window.innerHeight * 0.6 - rect.top, 0), rect.height - 48);
      progress.style.height = `${Math.max(seen, 0)}px`;
    };
    window.addEventListener("scroll", fill, { passive: true });
    window.addEventListener("resize", fill);
    fill();
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", fill);
      window.removeEventListener("resize", fill);
      flow.classList.remove("reveal-ready");
    };
  }, []);

  return { flowRef, progressRef };
}

export function LandingIntro({ sampleLoading, onOpenSample }: LandingIntroProps) {
  const { flowRef, progressRef } = useWalkthroughReveal();

  return (
    <div className="landing">
      <div className="landing-hero">
        <span className="landing-kicker">AWS Terraform · architecture review</span>
        <h1 id="landing-heading">
          A second opinion on your Terraform, <em>with the receipts.</em>
        </h1>
        <p className="landing-lede">
          ArchiBrief reads your Terraform and a short brief about the workload, then writes a review
          where every finding points to the resource it&apos;s about and the AWS guidance behind it.
          If it can&apos;t support a claim, it says so instead of guessing.
        </p>
        <div className="landing-cta-block">
          <div className="landing-actions">
            <a className="button primary" href="#samples">
              View sample review <span aria-hidden="true">→</span>
            </a>
            <a className="button secondary" href="#submit">
              Review your own Terraform
            </a>
          </div>
          <ul className="landing-badges">
            <li>Static analysis only</li>
            <li>Never touches your AWS account</li>
            <li>Every finding cites its source</li>
          </ul>
        </div>
      </div>

      <section
        className="landing-section landing-band"
        id="samples"
        aria-labelledby="samples-heading"
      >
        <div className="landing-section-head">
          <h2 id="samples-heading">Sample reviews</h2>
          <p>
            Complete reports on made-up architectures modeled on services you already know. Open one
            to see a real review.
          </p>
        </div>
        <div className="landing-samples">
          {samples.map((sample) => (
            <article
              key={sample.title}
              className={`landing-sample${sample.ready ? " available" : ""}`}
            >
              <div className="landing-sample-top">
                <span className="landing-sample-icon">
                  <SampleIcon icon={sample.icon} />
                </span>
                <div className="landing-tags">
                  <span className="landing-tag hypo">Hypothetical</span>
                  <span className={`landing-tag ${sample.ready ? "ready" : "soon"}`}>
                    {sample.ready ? "Ready" : "Coming soon"}
                  </span>
                </div>
              </div>
              <h3>{sample.title}</h3>
              <p>{sample.description}</p>
              <span className="landing-stack">{sample.stack}</span>
              {sample.ready ? (
                <button
                  className="landing-card-cta"
                  type="button"
                  onClick={onOpenSample}
                  disabled={sampleLoading}
                >
                  {sampleLoading ? "Loading sample…" : "View sample review"}{" "}
                  <span aria-hidden="true">→</span>
                </button>
              ) : (
                <span className="landing-card-cta disabled">Coming soon</span>
              )}
            </article>
          ))}
        </div>
        <p className="landing-disclaimer">
          Sample architectures are invented for this site. Not affiliated with, or based on the real
          systems of, Netflix or eBay.
        </p>
      </section>

      <section className="landing-section" id="how" aria-labelledby="how-heading">
        <div className="landing-flow-head">
          <span className="landing-label">How it works</span>
          <h2 id="how-heading">From Terraform to a review you can check</h2>
          <p>The same steps run for every review, including the payments sample above.</p>
        </div>
        <div className="landing-flow" ref={flowRef}>
          <span className="landing-flow-progress" ref={progressRef} aria-hidden="true" />
          <ol>
            <li className="landing-step">
              <div>
                <h3>You submit Terraform and a brief</h3>
                <p>
                  A Terraform archive plus a few sentences about the workload: traffic, how
                  available it must be, any data rules.
                </p>
                <p className="landing-step-note">
                  The brief matters. &quot;Customer-facing, can&apos;t go down&quot; turns a
                  single-AZ database from a footnote into a finding.
                </p>
              </div>
              <div className="landing-artifact" aria-label="Example submission">
                <div className="landing-artifact-head">
                  <span>payments-api.tar</span>
                  <span>input</span>
                </div>
                <div className="landing-artifact-body">
                  <ul className="landing-tree">
                    <li className="dir">main.tf</li>
                    <li className="dir">modules/</li>
                    <li className="indent">audit/s3.tf</li>
                    <li className="indent">api/lambda.tf</li>
                    <li className="indent">api/iam.tf</li>
                    <li className="indent">data/rds.tf</li>
                  </ul>
                  <p className="landing-brief">
                    <span className="landing-label">Workload brief</span>
                    Customer-facing payments API. Audit logs must be kept and never public. Moderate
                    traffic, business-critical.
                  </p>
                </div>
              </div>
            </li>

            <li className="landing-step">
              <div>
                <h3>Checks run, guidance is retrieved</h3>
                <p>
                  A trusted open-source scanner (Trivy) and ArchiBrief&apos;s own rules check the
                  Terraform. Then the matching passages are pulled from AWS Well-Architected and
                  security best-practice docs.
                </p>
                <p className="landing-step-note">
                  Anything outside the submitted code is marked as a gap, never assumed.
                </p>
              </div>
              <div className="landing-artifact" aria-label="Example check results">
                <div className="landing-artifact-head">
                  <span>checks</span>
                  <span>deterministic</span>
                </div>
                <div className="landing-artifact-body">
                  <ul className="landing-rules">
                    <li>
                      <span className="landing-status fail">FAIL</span>
                      <span>Lambda execution role grants s3:* on *</span>
                    </li>
                    <li>
                      <span className="landing-status fail">FAIL</span>
                      <span>Audit-log bucket has no public-access block</span>
                    </li>
                    <li>
                      <span className="landing-status pass">PASS</span>
                      <span>RDS storage encryption is declared</span>
                    </li>
                    <li>
                      <span className="landing-status gap">GAP</span>
                      <span>No CloudTrail in the code; may exist at org level</span>
                    </li>
                  </ul>
                  <p className="landing-retrieved">
                    Retrieved: <code>SEC03-BP02</code> · <code>SEC08-BP02</code> ·{" "}
                    <code>REL10-BP01</code>
                  </p>
                </div>
              </div>
            </li>

            <li className="landing-step">
              <div>
                <h3>You get a review with receipts</h3>
                <p>
                  A model weighs every result against your brief. Each citation is checked word for
                  word against the AWS text before anything is published.
                </p>
                <p className="landing-step-note">
                  Each finding: what it&apos;s about, the guidance it relies on, how sure it is, and
                  what to change.
                </p>
              </div>
              <div className="landing-artifact" aria-label="Example report finding">
                <div className="landing-artifact-head">
                  <span>report · finding</span>
                  <span>output</span>
                </div>
                <div className="landing-artifact-body landing-mini-finding">
                  <span className="landing-pill">High risk</span>
                  <h4>
                    Lambda execution role grants <code>s3:*</code> on <code>*</code>
                  </h4>
                  <dl>
                    <div>
                      <dt>Evidence</dt>
                      <dd className="landing-mono">
                        The inline policy contains Action s3:* and Resource *
                      </dd>
                    </div>
                    <div>
                      <dt>Cites</dt>
                      <dd>
                        <span className="landing-chip">SEC03-BP02</span> Grant least privilege
                        access
                      </dd>
                    </div>
                    <div>
                      <dt>Recommendation</dt>
                      <dd>
                        Scope the role to the specific S3 actions the function uses, on the audit
                        bucket only.
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            </li>
          </ol>
        </div>
      </section>
    </div>
  );
}

export function LandingClosing() {
  return (
    <div className="landing">
      <section
        className="landing-section landing-band"
        id="limits"
        aria-labelledby="checks-heading"
      >
        <div className="landing-band-grid">
          <div>
            <h2 id="checks-heading">What it checks</h2>
            <ul className="landing-check-list">
              <li>
                Public exposure<span>S3 public access, open security groups</span>
              </li>
              <li>
                Identity &amp; access<span>wildcard IAM, unconditioned trust</span>
              </li>
              <li>
                Encryption at rest<span>S3, EBS, RDS storage</span>
              </li>
              <li>
                Recoverability<span>backups, versioning, point-in-time recovery</span>
              </li>
              <li>
                Availability<span>single-AZ databases vs. your needs</span>
              </li>
              <li>
                Audit trail<span>CloudTrail and log validation</span>
              </li>
            </ul>
            <p className="landing-check-source">
              Checked by Trivy&apos;s trusted rules plus ArchiBrief&apos;s own, then weighed against
              your brief.
            </p>
          </div>
          <aside className="landing-trust" aria-labelledby="trust-heading">
            <h2 id="trust-heading">What ArchiBrief won&apos;t claim</h2>
            <p>
              <strong>It never touches your AWS account.</strong> It reads only the files you
              submit. No credentials, no calls into your environment.
            </p>
            <p>
              <strong>It can&apos;t see what you didn&apos;t submit.</strong> Org-level controls and
              unsubmitted modules show up as gaps, not passes or failures.
            </p>
            <p>
              <strong>It&apos;s not a compliance audit.</strong> It&apos;s a cited second opinion to
              help you decide what to fix first.
            </p>
          </aside>
        </div>
      </section>
    </div>
  );
}
