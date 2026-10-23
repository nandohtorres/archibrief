// Demo links contain only public IDs. Review capabilities remain in tab storage.
export function demoIdFromUrl(url: string): string | null {
  const id = new URL(url).searchParams.get("demo");
  return id && /^[a-z0-9-]{1,64}$/.test(id) ? id : null;
}

export function setDemoLocation(id: string | null): void {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("demo", id);
  else url.searchParams.delete("demo");
  url.hash = "";
  if (url.href !== window.location.href) window.history.pushState(null, "", url);
}
