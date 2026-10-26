// Report links contain only IDs. Review capabilities stay in browser storage.
export function demoIdFromUrl(url: string): string | null {
  const id = new URL(url).searchParams.get("demo");
  return id && /^[a-z0-9-]{1,64}$/.test(id) ? id : null;
}

// A URL names at most one report: a demo or one of this browser's reviews.
function setReportLocation(param: "demo" | "review", id: string | null): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("demo");
  url.searchParams.delete("review");
  if (id) url.searchParams.set(param, id);
  url.hash = "";
  if (url.href !== window.location.href) window.history.pushState(null, "", url);
}

export function setDemoLocation(id: string | null): void {
  setReportLocation("demo", id);
}

// Review links carry only the ID; opening one needs this browser's saved access.
export function reviewIdFromUrl(url: string): string | null {
  const id = new URL(url).searchParams.get("review");
  return id && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(id) ? id : null;
}

export function setReviewLocation(id: string | null): void {
  setReportLocation("review", id);
}
