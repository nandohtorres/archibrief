"use client";

import { useEffect, useState } from "react";
import { LOADING_FACTS } from "@/lib/facts";

const ROTATE_MS = 10_000;

// One fact at a time, rotating while a review runs. Not a live region:
// screen readers shouldn't be interrupted every ten seconds.
export function LoadingFacts() {
  const [index, setIndex] = useState<number | null>(null);
  useEffect(() => {
    // Picked on the client so the static page and the first render agree.
    setIndex(Math.floor(Math.random() * LOADING_FACTS.length));
    const timer = setInterval(
      () => setIndex((current) => ((current ?? 0) + 1) % LOADING_FACTS.length),
      ROTATE_MS,
    );
    return () => clearInterval(timer);
  }, []);
  if (index === null) return null;
  return (
    <aside className="loading-facts" aria-label="Did you know?">
      <span className="loading-facts-label">Did you know?</span>
      <p key={index}>{LOADING_FACTS[index]}</p>
    </aside>
  );
}
