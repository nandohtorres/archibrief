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
          <span className={`mode-badge ${apiConfigured ? "live" : "fixture"}`}>
            <span aria-hidden="true">●</span>{" "}
            {apiConfigured ? "Live API configured" : "Fixture mode"}
          </span>
          {apiConfigured && (
            <label className="admin-key-control" htmlFor="admin-key-input">
              Admin key
              <input
                id="admin-key-input"
                type="password"
                autoComplete="off"
                placeholder="Paste admin key"
                value={adminKey}
                onChange={(event) => onAdminKeyChange(event.target.value)}
              />
            </label>
          )}
          <label className="theme-control" htmlFor="theme-select">
            Theme
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
        <p>
          These controls expose each ADR-0032 state while most read/status endpoints are not yet
          deployed. They are not production navigation.
        </p>
      </details>
    </>
  );
}
