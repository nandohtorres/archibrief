// The architecture graph drawn in the report. It is built from the parsed
// Terraform without a model (backend/lambdas/rule_engine/architecture.py):
// nodes are resources the code creates, edges are references in the code,
// and findings sit on the resources they name.

export const ARCHITECTURE_LANES = [
  "internet",
  "edge",
  "network",
  "compute",
  "data",
  "security",
  "monitoring",
] as const;

export type ArchitectureLane = (typeof ARCHITECTURE_LANES)[number];

export const laneLabels: Record<ArchitectureLane, string> = {
  internet: "Internet",
  edge: "Edge",
  network: "Network",
  compute: "Compute",
  data: "Data",
  security: "Security & identity",
  monitoring: "Monitoring",
};

export interface ArchitectureNode {
  id: string;
  type: string;
  // The resource type in words ("security group").
  label: string;
  name: string;
  // The module path, empty in the root module.
  module?: string;
  lane: ArchitectureLane;
  // Resources folded into this one ("s3 bucket versioning").
  details: string[];
  findings: string[];
  // Set when count or for_each makes several copies.
  copies?: number | string;
}

export interface ArchitectureEdge {
  from: string;
  to: string;
}

export interface ArchitectureGraph {
  version: number;
  review_id?: string;
  lanes: ArchitectureLane[];
  nodes: ArchitectureNode[];
  edges: ArchitectureEdge[];
  account_findings: string[];
  truncated: boolean;
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isLane(value: unknown): value is ArchitectureLane {
  return typeof value === "string" && (ARCHITECTURE_LANES as readonly string[]).includes(value);
}

function isNode(value: unknown): value is ArchitectureNode {
  if (typeof value !== "object" || value === null) return false;
  const node = value as Record<string, unknown>;
  return (
    typeof node.id === "string" &&
    typeof node.type === "string" &&
    typeof node.label === "string" &&
    typeof node.name === "string" &&
    (node.module === undefined || typeof node.module === "string") &&
    isLane(node.lane) &&
    isStringList(node.details) &&
    isStringList(node.findings) &&
    (node.copies === undefined ||
      typeof node.copies === "number" ||
      typeof node.copies === "string")
  );
}

export function isArchitectureGraph(value: unknown): value is ArchitectureGraph {
  if (typeof value !== "object" || value === null) return false;
  const graph = value as Record<string, unknown>;
  if (
    graph.version !== 1 ||
    !Array.isArray(graph.lanes) ||
    !graph.lanes.every(isLane) ||
    !Array.isArray(graph.nodes) ||
    !graph.nodes.every(isNode) ||
    !Array.isArray(graph.edges) ||
    !isStringList(graph.account_findings) ||
    typeof graph.truncated !== "boolean"
  ) {
    return false;
  }
  const ids = new Set((graph.nodes as ArchitectureNode[]).map((node) => node.id));
  return graph.edges.every((edge) => {
    if (typeof edge !== "object" || edge === null) return false;
    const { from, to } = edge as Record<string, unknown>;
    return typeof from === "string" && typeof to === "string" && ids.has(from) && ids.has(to);
  });
}

// Layout: one column per lane, resources stacked in each column.
export const NODE_WIDTH = 176;
export const NODE_HEIGHT = 76;
const COLUMN_WIDTH = 228;
const ROW_GAP = 18;
const PADDING = 16;
const LANE_HEADER = 34;

export interface PlacedNode extends ArchitectureNode {
  x: number;
  y: number;
}

export interface PlacedEdge extends ArchitectureEdge {
  path: string;
}

export interface ArchitectureLayout {
  width: number;
  height: number;
  lanes: { lane: ArchitectureLane; x: number }[];
  nodes: PlacedNode[];
  edges: PlacedEdge[];
}

function edgePath(source: PlacedNode, target: PlacedNode): string {
  const sy = source.y + NODE_HEIGHT / 2;
  const ty = target.y + NODE_HEIGHT / 2;
  if (source.x === target.x) {
    // Same column: bow out to the right.
    const x = source.x + NODE_WIDTH;
    const bow = Math.min(46, 12 + Math.abs(ty - sy) / 10);
    return `M ${x} ${sy} C ${x + bow} ${sy}, ${x + bow} ${ty}, ${x + 2} ${ty}`;
  }
  const rightward = target.x > source.x;
  const sx = rightward ? source.x + NODE_WIDTH : source.x;
  const tx = rightward ? target.x - 2 : target.x + NODE_WIDTH + 2;
  const mid = (sx + tx) / 2;
  return `M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`;
}

export function layoutArchitecture(graph: ArchitectureGraph): ArchitectureLayout {
  const lanes = graph.lanes.map((lane, index) => ({ lane, x: PADDING + index * COLUMN_WIDTH }));
  const laneX = new Map(lanes.map(({ lane, x }) => [lane, x]));
  const rows = new Map<ArchitectureLane, number>();
  const ordered = [...graph.nodes].sort(
    (a, b) =>
      (a.module ?? "").localeCompare(b.module ?? "") ||
      a.label.localeCompare(b.label) ||
      a.name.localeCompare(b.name),
  );
  const nodes: PlacedNode[] = [];
  for (const node of ordered) {
    const x = laneX.get(node.lane);
    if (x === undefined) continue;
    const row = rows.get(node.lane) ?? 0;
    rows.set(node.lane, row + 1);
    nodes.push({ ...node, x, y: PADDING + LANE_HEADER + row * (NODE_HEIGHT + ROW_GAP) });
  }
  const placed = new Map(nodes.map((node) => [node.id, node]));
  const edges: PlacedEdge[] = [];
  for (const edge of graph.edges) {
    const source = placed.get(edge.from);
    const target = placed.get(edge.to);
    if (source && target) edges.push({ ...edge, path: edgePath(source, target) });
  }
  const tallest = Math.max(1, ...rows.values());
  return {
    width: PADDING * 2 + Math.max(0, lanes.length - 1) * COLUMN_WIDTH + NODE_WIDTH + 36,
    height: PADDING * 2 + LANE_HEADER + tallest * (NODE_HEIGHT + ROW_GAP) - ROW_GAP,
    lanes,
    nodes,
    edges,
  };
}
