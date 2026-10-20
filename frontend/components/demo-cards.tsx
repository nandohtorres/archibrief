"use client";

import { useEffect, useState } from "react";
import { fetchDemoIndex, type DemoEntry } from "@/lib/demos";

interface DemoCardsProps {
  // The demo being opened, if any; its card shows a loading label.
  openingId: string | null;
  onOpen: (entry: DemoEntry) => void;
  // "landing": the large cards in the landing page's demo section.
  variant?: "compact" | "landing";
}

// Finished reviews of real public Terraform, opened from static files: no
// admin key, no paid run (master list 15h, docs/demos.md).
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

  return (
    <section className="demo-cards" aria-labelledby="demo-cards-heading">
      <h3 className="example-heading" id="demo-cards-heading">
        See a finished review
      </h3>
      <p className="demo-cards-note">
        Real public Terraform, reviewed once and checked by hand. Opening one is free and starts no
        new review.
      </p>
      <div className="demo-card-grid">
        {demos.map((demo) => (
          <button
            key={demo.id}
            type="button"
            className="demo-card"
            disabled={openingId !== null}
            onClick={() => onOpen(demo)}
          >
            <strong>{openingId === demo.id ? "Opening…" : demo.title}</strong>
            <span>{demo.subtitle}</span>
            <small>
              {demo.source} · {demo.license}
            </small>
          </button>
        ))}
      </div>
    </section>
  );
}
