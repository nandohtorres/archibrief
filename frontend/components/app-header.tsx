import type { AppScreen } from "@/lib/workflow";

type ThemeChoice = "light" | "dark";

interface AppHeaderProps {
  apiConfigured: boolean;
  screen: AppScreen;
  theme: ThemeChoice;
  onThemeChange: (theme: ThemeChoice) => void;
  onPreview: (screen: AppScreen) => void;
  // The logo goes back to the home page from any screen.
  onHome: () => void;
  // Scrolls to a home page section, going home first from other screens.
  onSection: (id: string) => void;
}

const previews: Array<{ screen: AppScreen; label: string }> = [
  { screen: "submission", label: "Submit" },
  { screen: "preflight", label: "Preflight" },
  { screen: "progress", label: "Progress" },
  { screen: "report", label: "Report" },
  { screen: "failure", label: "Failure" },
];

const sections: Array<{ id: string; label: string }> = [
  { id: "how", label: "How it works" },
  { id: "samples", label: "Demo" },
  { id: "submit", label: "Submit yours" },
];

const nextTheme: Record<ThemeChoice, ThemeChoice> = {
  light: "dark",
  dark: "light",
};

const themeNames: Record<ThemeChoice, string> = {
  light: "Light",
  dark: "Dark",
};

// Stacked layers: the architecture a review looks through.
export function BrandEmblem() {
  return (
    <svg className="brand-emblem" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 3 29 10 16 17 3 10Z" fill="currentColor" />
      <path
        d="M3 15.5 16 22.5 29 15.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinejoin="round"
        opacity="0.65"
      />
      <path
        d="M3 21 16 28 29 21"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinejoin="round"
        opacity="0.35"
      />
    </svg>
  );
}

function ThemeIcon({ theme }: { theme: ThemeChoice }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {theme === "dark" && <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />}
      {theme === "light" && (
        <>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </>
      )}
    </svg>
  );
}

export function AppHeader({
  apiConfigured,
  screen,
  theme,
  onThemeChange,
  onPreview,
  onHome,
  onSection,
}: AppHeaderProps) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="site-header">
        <button
          type="button"
          className="brand-lockup brand-home"
          aria-label="ArchiBrief home"
          onClick={onHome}
        >
          <BrandEmblem />
          <span className="brand-text">
            <strong className="brand-name">ArchiBrief</strong>
            <small className="brand-tagline">Your AWS architecture, briefed</small>
          </span>
        </button>
        <div className="header-controls">
          {!apiConfigured && (
            <span className="mode-badge fixture">
              <span aria-hidden="true">●</span> Fixture mode
            </span>
          )}
          <nav className="site-nav" aria-label="Sections">
            {sections.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                onClick={(event) => {
                  event.preventDefault();
                  onSection(section.id);
                }}
              >
                {section.label}
              </a>
            ))}
          </nav>
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Theme: ${themeNames[theme]}. Switch to ${themeNames[nextTheme[theme]]}`}
            title={`Theme: ${themeNames[theme]}`}
            onClick={() => onThemeChange(nextTheme[theme])}
          >
            <ThemeIcon theme={theme} />
          </button>
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
