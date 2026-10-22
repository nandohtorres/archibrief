"use client";

import { useEffect, useState } from "react";
import { fetchDemoIndex, type DemoEntry } from "@/lib/demos";

interface DemoCardsProps {
  // The demo being opened, if any; its card shows a loading label.
  openingId: string | null;
  onOpen: (entry: DemoEntry) => void;
  // "landing": the large cards in the landing page's demo section.
  // "compact": the small strip at the top of the submission form.
  variant?: "compact" | "landing";
}

// Finished reviews of real public Terraform, opened from static files: no
// admin key, no paid run (docs/demos.md).
export function DemoCards({ openingId, onOpen, variant = "compact" }: DemoCardsProps) {
  const [demos, setDemos] = useState<DemoEntry[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetchDemoIndex()
      .then((entries) => {
        if (active) setDemos(entries);
      })
      .catch((error: unknown) => {
        console.error("demo index could not be loaded", error);
        if (active) setLoadFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loadFailed || demos.length === 0) return null;

  if (variant === "landing") {
    return (
      <div className="landing-samples">
        {demos.map((demo) => (
          <article key={demo.id} className="landing-sample available">
            <div className="landing-tags">
              <span className="landing-tag ready">Real public code</span>
              <span className="landing-tag hypo">
                {demo.reviewerNotes?.length
                  ? `${demo.reviewerNotes.length} reviewer note${demo.reviewerNotes.length === 1 ? "" : "s"}`
                  : "Checked by hand"}
              </span>
            </div>
            <h3>{demo.title}</h3>
            <p>{demo.subtitle}</p>
            <span className="landing-stack">
              {demo.source} · {demo.license}
            </span>
            <button
              className="landing-card-cta"
              type="button"
              disabled={openingId !== null}
              aria-label={`${demo.title}: open the review`}
              onClick={() => onOpen(demo)}
            >
              {openingId === demo.id ? "Opening…" : "Open the review"}{" "}
              <span aria-hidden="true">→</span>
            </button>
          </article>
        ))}
      </div>
    );
  }

  // The submission form's strip: kept small so it reads as a side door,
  // with the divider into the form's own fields.
  return (
    <>
      <section className="demo-strip" aria-labelledby="demo-strip-heading">
        <div className="demo-strip-header">
          <h3 id="demo-strip-heading">No Terraform? Open a finished example</h3>
        </div>
        <div className="demo-strip-grid">
          {demos.map((demo) => {
            const label = demo.shortTitle ?? demo.title;
            return (
              <button
                key={demo.id}
                type="button"
                className="demo-strip-button"
                disabled={openingId !== null}
                aria-label={`${label}: open the full report`}
                onClick={() => onOpen(demo)}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M14 3h7v7" />
                  <path d="M10 14 21 3" />
                  <path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5" />
                </svg>
                <span>
                  <strong>{openingId === demo.id ? "Opening…" : label}</strong>
                  <small>{demo.tag ?? demo.subtitle}</small>
                </span>
              </button>
            );
          })}
        </div>
      </section>
      <div className="form-divider" role="separator">
        <span>or submit your own</span>
      </div>
    </>
  );
}
