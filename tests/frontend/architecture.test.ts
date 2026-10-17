import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  NODE_HEIGHT,
  NODE_WIDTH,
  isArchitectureGraph,
  layoutArchitecture,
  type ArchitectureGraph,
} from "../../frontend/lib/architecture";

const DEMOS = join(__dirname, "../../frontend/public/demos");

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(join(DEMOS, path), "utf-8"));
}

const index = readJson("demos.json") as { demos: { id: string }[] };

function graph(overrides: Partial<ArchitectureGraph> = {}): ArchitectureGraph {
  return {
    version: 1,
    lanes: ["network", "compute"],
    nodes: [
      {
        id: "vpc",
        type: "aws_vpc",
        label: "vpc",
        name: "main",
        lane: "network",
        details: [],
        findings: [],
      },
      {
        id: "sg",
        type: "aws_security_group",
        label: "security group",
        name: "web",
        lane: "network",
        details: [],
        findings: ["f1"],
      },
      {
        id: "ec2",
        type: "aws_instance",
        label: "instance",
        name: "proxy",
        lane: "compute",
        details: [],
        findings: [],
        copies: 2,
      },
    ],
    edges: [
      { from: "ec2", to: "sg" },
      { from: "sg", to: "vpc" },
    ],
    account_findings: [],
    truncated: false,
    ...overrides,
  };
}

describe("architecture graph (lib/architecture.ts)", () => {
  it("ships a valid graph for every demo, matching its report", () => {
    for (const { id } of index.demos) {
      const shipped = readJson(`architecture/${id}.json`);
      const report = readJson(`reports/${id}.json`) as {
        review_id: string;
        findings: { record: { finding_id: string } }[];
      };
      expect(isArchitectureGraph(shipped)).toBe(true);
      const built = shipped as ArchitectureGraph;
      expect(built.review_id).toBe(report.review_id);
      const ids = new Set(report.findings.map((f) => f.record.finding_id));
      const placed = [
        ...built.nodes.flatMap((n) => n.findings),
        ...built.account_findings,
      ];
      // Every finding is either on a resource or listed as account-wide.
      for (const findingId of ids) expect(placed).toContain(findingId);
      for (const findingId of placed) expect(ids.has(findingId)).toBe(true);
    }
  });

  it("rejects malformed graphs", () => {
    expect(isArchitectureGraph(graph())).toBe(true);
    expect(isArchitectureGraph({ ...graph(), version: 2 })).toBe(false);
    expect(
      isArchitectureGraph(graph({ edges: [{ from: "ec2", to: "missing" }] })),
    ).toBe(false);
    expect(
      isArchitectureGraph(
        graph({ lanes: ["network", "nowhere" as "network"] }),
      ),
    ).toBe(false);
    const [first, ...rest] = graph().nodes;
    expect(
      isArchitectureGraph(
        graph({
          nodes: [{ ...first, findings: "f1" as unknown as string[] }, ...rest],
        }),
      ),
    ).toBe(false);
    expect(isArchitectureGraph(null)).toBe(false);
  });

  it("lays out one column per lane with no overlapping nodes", () => {
    const layout = layoutArchitecture(graph());
    const [network, compute] = layout.lanes;
    expect(compute.x).toBeGreaterThan(network.x + NODE_WIDTH);
    const inNetwork = layout.nodes.filter((n) => n.lane === "network");
    expect(inNetwork.map((n) => n.x)).toEqual([network.x, network.x]);
    const [upper, lower] = [...inNetwork].sort((a, b) => a.y - b.y);
    expect(lower.y).toBeGreaterThanOrEqual(upper.y + NODE_HEIGHT);
    for (const node of layout.nodes) {
      expect(node.x + NODE_WIDTH).toBeLessThanOrEqual(layout.width);
      expect(node.y + NODE_HEIGHT).toBeLessThanOrEqual(layout.height);
    }
  });

  it("draws every edge between placed nodes", () => {
    const layout = layoutArchitecture(graph());
    expect(layout.edges).toHaveLength(2);
    for (const edge of layout.edges)
      expect(edge.path).toMatch(/^M [\d.]+ [\d.]+ C /);
  });
});
