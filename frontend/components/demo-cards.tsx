"use client";

import { useEffect, useState } from "react";
import { fetchDemoIndex, type DemoEntry } from "@/lib/demos";

interface DemoCardsProps {
  // The demo being opened, if any; its card shows a loading label.
  openingId: string | null;
  onOpen: (entry: DemoEntry) => void;
}

// Finished reviews of real public Terraform, opened from static files: no
// admin key, no paid run (master list 15h, docs/demos.md).
export function DemoCards({ openingId, onOpen }: DemoCardsProps) {
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
