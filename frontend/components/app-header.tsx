import type { AppScreen } from "@/lib/workflow";

type ThemeChoice = "system" | "light" | "dark";

interface AppHeaderProps {
  apiConfigured: boolean;
  screen: AppScreen;
  theme: ThemeChoice;
  onThemeChange: (theme: ThemeChoice) => void;
  onPreview: (screen: AppScreen) => void;
  adminKey: string;
  onAdminKeyChange: (value: string) => void;
}

const previews: Array<{ screen: AppScreen; label: string }> = [
  { screen: "submission", label: "Submit" },
  { screen: "preflight", label: "Preflight" },
  { screen: "progress", label: "Progress" },
  { screen: "report", label: "Report" },
  { screen: "failure", label: "Failure" },
];

export function AppHeader({
  apiConfigured,
  screen,
  theme,
  onThemeChange,
  onPreview,
  adminKey,
  onAdminKeyChange,
}: AppHeaderProps) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="site-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            A
          </span>
          <div>
            <strong>ArchiBrief</strong>
            <span>Auditable AWS architecture review</span>
          </div>
        </div>
        <div className="header-controls">
          {!apiConfigured && (
            <span className="mode-badge fixture">
              <span aria-hidden="true">●</span> Fixture mode
            </span>
          )}
          {apiConfigured && (
            <div className="admin-key-control">
              <label htmlFor="admin-key-input">Admin key</label>
              <input
                id="admin-key-input"
                type="password"
                autoComplete="off"
                placeholder="Paste admin key"
                value={adminKey}
                onChange={(event) => onAdminKeyChange(event.target.value)}
              />
              {/* Kept for this tab only (lib/admin-key.ts); this clears it now. */}
              {adminKey && (
                <button type="button" className="button quiet" onClick={() => onAdminKeyChange("")}>
                  Forget key
                </button>
              )}
            </div>
          )}
          <label className="theme-control" htmlFor="theme-select">
            <span className="theme-label">Theme</span>
            <select
              id="theme-select"
              value={theme}
              onChange={(event) => onThemeChange(event.target.value as ThemeChoice)}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
        </div>
      </header>
      {/* Development aid only - never rendered in a build pointed at a real API. */}
      {!apiConfigured && (
        <details className="fixture-controls">
          <summary>Fixture preview controls</summary>
          <div className="preview-buttons" aria-label="Preview application state">
            {previews.map((preview) => (
              <button
                type="button"
                key={preview.screen}
                aria-pressed={screen === preview.screen}
                onClick={() => onPreview(preview.screen)}
              >
                {preview.label}
              </button>
            ))}
          </div>
          <p>Jump to any screen of the flow with fixture data. Development builds only.</p>
        </details>
      )}
    </>
  );
}
