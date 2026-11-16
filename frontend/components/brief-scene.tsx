// Draws the Stakeholder Brief's farm pictures (data: lib/brief-scenes.ts).
// Pictures are illustrations, not a map of the system.

import { SCENES, type SceneItem, type ScenePanelData } from "@/lib/brief-scenes";
import type { SceneKey } from "@/lib/stakeholder-brief";

function SceneShape({ item }: { item: SceneItem }) {
  const dash = "unknown" in item && item.unknown ? "4 3" : undefined;
  switch (item.kind) {
    case "road":
      return (
        <g className="scene-road">
          <rect x="0" y={item.y} width="200" height="14" />
          <text x="196" y={item.y + 10} textAnchor="end">
            {item.label}
          </text>
        </g>
      );
    case "building":
      return (
        <g className="scene-building" strokeDasharray={dash}>
          <path
            d={`M${item.x} ${item.y + 22} L${item.x + 30} ${item.y} L${item.x + 60} ${item.y + 22} V${item.y + 56} H${item.x} Z`}
          />
          <text x={item.x + 30} y={item.y + 70} textAnchor="middle">
            {item.label}
          </text>
        </g>
      );
    case "gate":
      return (
        <g className="scene-gate">
          <rect x={item.x} y={item.y} width="44" height="18" rx="2" />
          <path
            d={`M${item.x + 11} ${item.y} V${item.y + 18} M${item.x + 22} ${item.y} V${item.y + 18} M${item.x + 33} ${item.y} V${item.y + 18}`}
          />
          <text x={item.x + 22} y={item.y - 4} textAnchor="middle">
            {item.label}
          </text>
        </g>
      );
    case "route":
      return (
        <g className="scene-route" strokeDasharray={dash}>
          <line x1={item.x1} y1={item.y1} x2={item.x2} y2={item.y2} />
          <text x={(item.x1 + item.x2) / 2 + 4} y={(item.y1 + item.y2) / 2 - 4}>
            {item.label}
          </text>
        </g>
      );
    case "tag":
      return (
        <g className="scene-tag" strokeDasharray={dash}>
          <rect x={item.x} y={item.y} width={item.label.length * 5.4 + 12} height="18" rx="3" />
          <text x={item.x + 6} y={item.y + 12.5}>
            {item.label}
          </text>
        </g>
      );
    case "book":
      return (
        <g className="scene-book" strokeDasharray={dash}>
          <rect x={item.x} y={item.y} width="44" height="34" rx="2" />
          {item.sealed && <circle cx={item.x + 40} cy={item.y + 30} r="6" className="scene-seal" />}
          {"unknown" in item && item.unknown && (
            <text x={item.x + 22} y={item.y + 23} textAnchor="middle" className="scene-q">
              ?
            </text>
          )}
          <text x={item.x + 22} y={item.y + 48} textAnchor="middle">
            {item.label}
          </text>
        </g>
      );
    case "stack":
      return (
        <g className="scene-book">
          {[0, 6, 12].map((offset) => (
            <rect
              key={offset}
              x={item.x + offset}
              y={item.y + offset}
              width="44"
              height="30"
              rx="2"
            />
          ))}
          <text x={item.x + 28} y={item.y + 60} textAnchor="middle">
            {item.label}
          </text>
        </g>
      );
    case "check":
      return (
        <g className="scene-check">
          <rect x={item.x} y={item.y} width="40" height="24" rx="4" />
          <path d={`M${item.x + 12} ${item.y + 12} l6 6 l10 -12`} />
          <text x={item.x + 20} y={item.y - 4} textAnchor="middle">
            {item.label}
          </text>
        </g>
      );
  }
}

function ScenePanel({ title, panel }: { title: string; panel: ScenePanelData }) {
  return (
    <figure className="scene-panel">
      <figcaption>
        <strong>{title}</strong>
      </figcaption>
      <svg viewBox="0 0 200 120" role="img" aria-label={`${title}: ${panel.caption}`}>
        {panel.items.map((item, index) => (
          <SceneShape key={index} item={item} />
        ))}
      </svg>
      <p>{panel.caption}</p>
    </figure>
  );
}

export function BriefScene({ scene }: { scene: SceneKey }) {
  const { plans, proposed } = SCENES[scene];
  return (
    <div className="brief-scene">
      <ScenePanel title="In the submitted plans" panel={plans} />
      <ScenePanel title="Proposed change" panel={proposed} />
      <p className="brief-scene-note">
        An illustration, not a map of your system. Dashed parts with “?” were not confirmed.
      </p>
    </div>
  );
}
