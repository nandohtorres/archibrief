"use client";

import { useEffect, useRef, type ReactNode } from "react";

// Landing content: an editorial hero, sample cards, check marks, a
// numbered walkthrough and a checks list. Split in two so the submission form
// sits where the story turns into the product: LandingIntro (hero, samples,
// how it works) above the form, LandingClosing (what it checks, limits)
// below it.

interface LandingIntroProps {
  sampleLoading: boolean;
  onOpenSample: () => void;
  // The real demo reviews (DemoCards).
  demos: ReactNode;
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

export function LandingIntro({ sampleLoading, onOpenSample, demos }: LandingIntroProps) {
  const { flowRef, progressRef } = useWalkthroughReveal();

  return (
    <div className="landing">
      <div className="landing-hero">
        <span className="landing-kicker">
          AWS Terraform reviews · for engineers and the people they report to
        </span>
        <h1 id="landing-heading">
          A second opinion on your AWS architecture, <em>with the receipts.</em>
        </h1>
        <p className="landing-lede">
          ArchiBrief reads your Terraform and a short brief about the workload, then explains in
          plain language what&apos;s exposed, what could fail, and why each fix matters. Each
          finding shows the code it&apos;s based on and, where it relies on AWS guidance, the exact
          passage, so you can check it.
        </p>
        <div className="landing-cta-block">
          <div className="landing-actions">
            <button
              className="button primary"
              type="button"
              onClick={onOpenSample}
              disabled={sampleLoading}
            >
              {sampleLoading ? "Loading review…" : "See a real review"}{" "}
              <span aria-hidden="true">→</span>
            </button>
            <a className="button secondary" href="#submit">
              Submit your own Terraform
            </a>
          </div>
          <ul className="landing-badges">
            <li>Never touches your AWS account</li>
            <li>Evidence shown with each finding</li>
            <li>AI mistakes shown, not hidden</li>
          </ul>
        </div>
      </div>

      <section
        className="landing-section landing-band"
        id="readers"
        aria-labelledby="readers-heading"
      >
        <div className="landing-section-head">
          <h2 id="readers-heading">One review, two readers</h2>
          <p>Built for the engineer who fixes it and the person who has to say yes.</p>
        </div>
        <div className="landing-samples">
          <article className="landing-sample">
            <span className="landing-label">For engineers</span>
            <h3>The evidence dashboard</h3>
            <p>
              Each finding with the resource it&apos;s about, the AWS guidance it cites, how sure it
              is, and the exact change to make.
            </p>
          </article>
          <article className="landing-sample">
            <span className="landing-label">For everyone else</span>
            <h3>The guided report</h3>
            <p className="landing-quote">
              &ldquo;Your proxy can be tricked into handing over its AWS credentials, and those
              credentials can read every bucket. That&apos;s the pattern behind the 2019 Capital One
              breach.&rdquo;
            </p>
          </article>
          <article className="landing-sample">
            <span className="landing-label">See it, then ask it</span>
            <h3>Diagram and questions</h3>
            <p>
              A diagram drawn from your code with each finding pinned where it applies. Ask
              follow-ups and push back; every answer cites the review.
            </p>
          </article>
        </div>
      </section>

      <section className="landing-section" id="how" aria-labelledby="how-heading">
        <div className="landing-flow-head">
          <span className="landing-label">How it works</span>
          <h2 id="how-heading">From Terraform to a review you can check</h2>
          <p>The same steps run for every review, including the real ones above.</p>
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
                  The brief matters. &quot;Card data must never be reachable from the internet&quot;
                  turns a loose role from a footnote into the top risk.
                </p>
              </div>
              <div className="landing-artifact" aria-label="Example submission">
                <div className="landing-artifact-head">
                  <span>cloud_breach_s3.tar</span>
                  <span>input</span>
                </div>
                <div className="landing-artifact-body">
                  <ul className="landing-tree">
                    <li className="dir">terraform/</li>
                    <li className="indent">ec2.tf</li>
                    <li className="indent">s3.tf</li>
                    <li className="indent">vpc.tf</li>
                    <li className="indent">variables.tf</li>
                  </ul>
                  <p className="landing-brief">
                    <span className="landing-label">Workload brief</span>A bank&apos;s card
                    platform. One nginx proxy faces the internet; an S3 bucket holds cardholder data
                    and must never be reachable from it. PCI-DSS applies.
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
                      <span>Proxy&apos;s role has AmazonS3FullAccess</span>
                    </li>
                    <li>
                      <span className="landing-status fail">FAIL</span>
                      <span>Proxy doesn&apos;t require IMDSv2 tokens</span>
                    </li>
                    <li>
                      <span className="landing-status fail">FAIL</span>
                      <span>Card-data bucket public access not fully blocked</span>
                    </li>
                    <li>
                      <span className="landing-status gap">GAP</span>
                      <span>No CloudTrail in the code; may exist at org level</span>
                    </li>
                  </ul>
                  <p className="landing-retrieved">
                    Retrieved: <code>SEC03-BP02</code> · <code>SEC06-BP05</code> ·{" "}
                    <code>SEC05-BP02</code>
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
                  <h4>The proxy&apos;s role can read every bucket, including the card data</h4>
                  <dl>
                    <div>
                      <dt>Evidence</dt>
                      <dd className="landing-mono">
                        aws_iam_role &quot;cg-banking-WAF-Role&quot; is used by the EC2 proxy and
                        has AmazonS3FullAccess attached
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
                        Replace the managed policy with one that names only the actions and buckets
                        the proxy uses.
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            </li>
          </ol>
        </div>
      </section>

      <section
        className="landing-section landing-band"
        id="samples"
        aria-labelledby="samples-heading"
      >
        <div className="landing-section-head">
          <h2 id="samples-heading">Real reviews of real public code</h2>
          <p>
            Three open-source AWS projects, reviewed by ArchiBrief and then checked by hand. Where
            the AI got something wrong, the review says so.
          </p>
        </div>
        {demos}
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
              <strong>It&apos;s not an audit or a certification.</strong> It&apos;s an
              evidence-backed architecture review that helps you decide what to fix first, and
              explains why.
            </p>
          </aside>
        </div>
      </section>
    </div>
  );
}
