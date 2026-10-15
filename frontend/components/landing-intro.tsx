// Landing content (master-list #8, design option A "editorial" — see
// frontend/design/landing-options/). Sits above the submission form on
// the first screen; the form itself is the "Review your own Terraform"
// section further down the same page.

interface LandingIntroProps {
  sampleLoading: boolean;
  onOpenSample: () => void;
}

interface SampleCard {
  title: string;
  description: string;
  stack: string;
  ready: boolean;
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
  },
  {
    title: "Video streaming platform",
    description:
      "A Netflix-style service: media origins behind a CDN, a transcoding pipeline, and per-viewer watch history.",
    stack: "CloudFront · S3 · Lambda · MediaConvert · DynamoDB",
    ready: false,
  },
  {
    title: "Online marketplace",
    description:
      "An eBay-style marketplace: listings, search, bidding, and a payments boundary with audit retention.",
    stack: "ALB · ECS · RDS · OpenSearch · SQS",
    ready: false,
  },
];

export function LandingIntro({ sampleLoading, onOpenSample }: LandingIntroProps) {
  return (
    <div className="landing">
      <div className="landing-hero">
        <span className="landing-kicker">AWS Terraform · architecture review</span>
        <h1 id="landing-heading">
          A second opinion on your AWS architecture, <em>with the receipts.</em>
        </h1>
        <p className="landing-lede">
          ArchiBrief reads your Terraform and a short brief about the workload, then writes a review
          where every finding points to the exact resource it is about and the AWS guidance it
          relies on. If it can&apos;t support a claim, it says so instead of guessing.
        </p>
        <div className="landing-actions">
          <button
            className="button primary landing-cta"
            type="button"
            onClick={onOpenSample}
            disabled={sampleLoading}
          >
            {sampleLoading ? "Loading sample…" : "View sample review"}{" "}
            <span aria-hidden="true">→</span>
          </button>
          <a className="landing-text-link" href="#submit">
            Review your own Terraform
          </a>
        </div>
        <p className="landing-note">
          Static analysis only.{" "}
          <span>ArchiBrief reads the files you submit and never connects to your AWS account.</span>
        </p>
      </div>

      <section className="landing-section" id="samples" aria-labelledby="samples-heading">
        <div className="landing-section-head">
          <h2 id="samples-heading">Sample reviews</h2>
          <p>Full reports on hypothetical workloads. Open one to see what a review looks like.</p>
        </div>
        <div className="landing-samples">
          {samples.map((sample) => (
            <article
              key={sample.title}
              className={`landing-sample${sample.ready ? " available" : ""}`}
            >
              <div className="landing-tags">
                <span className="landing-tag hypo">Hypothetical</span>
                <span className={`landing-tag ${sample.ready ? "ready" : "soon"}`}>
                  {sample.ready ? "Ready" : "Coming soon"}
                </span>
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
                  Open sample review <span aria-hidden="true">→</span>
                </button>
              ) : (
                <span className="landing-card-cta disabled">Coming soon</span>
              )}
            </article>
          ))}
        </div>
        <p className="landing-disclaimer">
          Samples are invented architectures written for this site. They are not affiliated with, or
          based on the real systems of, Netflix or eBay.
        </p>
      </section>

      <section className="landing-section" id="how" aria-labelledby="how-heading">
        <div className="landing-section-head">
          <h2 id="how-heading">How a review is built</h2>
          <p>Three layers, each checking the one before it.</p>
        </div>
        <div className="landing-columns">
          <div>
            <span className="landing-num">01</span>
            <h3>Deterministic checks</h3>
            <p>
              16 rule checks run over the parsed Terraform: public-access blocks, wildcard IAM,
              unencrypted storage, single-AZ databases, missing log validation, and more. Same
              input, same result.
            </p>
          </div>
          <div>
            <span className="landing-num">02</span>
            <h3>Retrieved guidance</h3>
            <p>
              Relevant passages are pulled from the AWS Well-Architected Framework and AWS security
              documentation, so the review argues from the source, not from memory.
            </p>
          </div>
          <div>
            <span className="landing-num">03</span>
            <h3>Grounded review</h3>
            <p>
              A language model weighs the findings against your brief. Every citation it emits is
              re-checked against the retrieved passages before the report is published.
            </p>
          </div>
        </div>

        <figure className="landing-example" aria-label="Example finding">
          <span className="landing-example-label">Example finding · from the payments sample</span>
          <blockquote>
            Lambda execution role grants <code>s3:*</code> on <code>*</code>.
          </blockquote>
          <dl>
            <div>
              <dt>Evidence</dt>
              <dd>
                The submitted inline policy contains <code>Action: s3:*</code> and{" "}
                <code>Resource: *</code>.
              </dd>
            </div>
            <div>
              <dt>Cites</dt>
              <dd>
                AWS IAM best practices · Apply least-privilege permissions{" "}
                <span className="landing-muted">(Well-Architected SEC03-BP02)</span>
              </dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>
                High <span className="landing-muted">· deterministic rule, matching guidance</span>
              </dd>
            </div>
          </dl>
        </figure>
      </section>

      <section
        className="landing-section landing-limits"
        id="limits"
        aria-labelledby="limits-heading"
      >
        <div>
          <h2 id="limits-heading">What it can and can&apos;t tell you</h2>
          <p>A review is only as good as what it can see. ArchiBrief is explicit about that.</p>
        </div>
        <ul>
          <li>
            <strong>It never touches your AWS account.</strong>
            <span>
              No credentials, no calls into your environment. It reads only what you submit.
            </span>
          </li>
          <li>
            <strong>Every finding cites its evidence.</strong>
            <span>What in the code it is about, plus the AWS passage it relies on.</span>
          </li>
          <li>
            <strong>Gaps are labeled, not guessed.</strong>
            <span>
              If a control could live outside the submitted code, such as an organization-wide
              CloudTrail, the finding says so and is marked &quot;not observable&quot;.
            </span>
          </li>
          <li>
            <strong>It is not a compliance certification.</strong>
            <span>It&apos;s a second opinion to inform a decision, not an audit.</span>
          </li>
        </ul>
      </section>
    </div>
  );
}
