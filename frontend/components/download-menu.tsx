"use client";

import { useEffect, useId, useRef, useState } from "react";

interface DownloadMenuProps {
  onReport: () => void;
  onJson: () => void;
}

// One "Download" button that opens the two download choices. Closes on a
// choice, Escape, or a click outside it.
export function DownloadMenu({ onReport, onJson }: DownloadMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function choose(action: () => void) {
    setOpen(false);
    action();
  }

  return (
    <div className="download-menu" ref={rootRef}>
      <button
        ref={toggleRef}
        className="button primary"
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
      >
        Download <span aria-hidden="true">▾</span>
      </button>
      <div id={listId} className="download-menu-list" hidden={!open}>
        <button type="button" onClick={() => choose(onReport)}>
          Download report
          <small>Readable HTML, with any chat</small>
        </button>
        <button type="button" onClick={() => choose(onJson)}>
          Export JSON
          <small>The full findings data</small>
        </button>
      </div>
    </div>
  );
}
