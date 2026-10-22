// Build-time preview switches; the server independently enforces its gates.
export const turnstileSiteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? "";
export const publicSubmissionEnabled =
  process.env.NEXT_PUBLIC_PUBLIC_ACCESS_ENABLED === "true" && Boolean(turnstileSiteKey);
