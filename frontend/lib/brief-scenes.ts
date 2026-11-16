// Farm pictures for the Stakeholder Brief (ADR-0062), as data. Each scene
// has two labeled panels: what the submitted plans show, and the proposed
// change. Anything the review could not confirm (a route, a control kept
// outside the code) is marked unknown and drawn dashed with a "?", never
// as a deployed fact. components/brief-scene.tsx draws them.

import type { SceneKey } from "./stakeholder-brief";

export type SceneItem =
  | { kind: "building"; x: number; y: number; label: string; unknown?: boolean }
  | { kind: "road"; y: number; label: string }
  | {
      kind: "route";
      x1: number;
      y1: number;
      x2: number;
      y2: number;
      label: string;
      unknown?: boolean;
    }
  | { kind: "gate"; x: number; y: number; label: string }
  | { kind: "tag"; x: number; y: number; label: string; unknown?: boolean }
  | { kind: "book"; x: number; y: number; label: string; sealed?: boolean; unknown?: boolean }
  | { kind: "stack"; x: number; y: number; label: string }
  | { kind: "check"; x: number; y: number; label: string };

export interface ScenePanelData {
  items: SceneItem[];
  caption: string;
}

export interface Scene {
  plans: ScenePanelData;
  proposed: ScenePanelData;
}

export const SCENES: Record<SceneKey, Scene> = {
  "gate-rule": {
    plans: {
      items: [
        { kind: "road", y: 100, label: "public road" },
        { kind: "building", x: 120, y: 18, label: "service" },
        { kind: "gate", x: 70, y: 46, label: "rule: anyone" },
        { kind: "route", x1: 40, y1: 98, x2: 70, y2: 64, label: "road to gate?", unknown: true },
      ],
      caption: "The gate's rule lets anyone knock. Whether a road reaches it was not confirmed.",
    },
    proposed: {
      items: [
        { kind: "road", y: 100, label: "public road" },
        { kind: "building", x: 120, y: 18, label: "service" },
        { kind: "gate", x: 70, y: 46, label: "rule: named only" },
      ],
      caption: "The rule names who may knock. Other gates are not changed by this.",
    },
  },
  "missing-latch": {
    plans: {
      items: [
        { kind: "building", x: 70, y: 18, label: "feed store" },
        { kind: "tag", x: 20, y: 78, label: "latch 1" },
        { kind: "tag", x: 110, y: 78, label: "latch 2 not shown", unknown: true },
      ],
      caption:
        "The plans don't show the second latch fitted. Other locks were not shown to be open.",
    },
    proposed: {
      items: [
        { kind: "building", x: 70, y: 18, label: "feed store" },
        { kind: "tag", x: 20, y: 78, label: "latch 1" },
        { kind: "tag", x: 110, y: 78, label: "latch 2" },
      ],
      caption: "Both latches in place. People with keys still get in.",
    },
  },
  "open-store": {
    plans: {
      items: [
        { kind: "building", x: 70, y: 14, label: "feed store" },
        { kind: "tag", x: 50, y: 74, label: "sign: anyone may enter" },
      ],
      caption:
        "The plans' policy says anyone may enter. Another lock may override it; who has entered was not checked.",
    },
    proposed: {
      items: [
        { kind: "building", x: 70, y: 14, label: "feed store" },
        { kind: "tag", x: 50, y: 74, label: "sign: named staff only" },
      ],
      caption: "Only named people and services may enter.",
    },
  },
  "listed-address": {
    plans: {
      items: [
        { kind: "road", y: 100, label: "public road" },
        { kind: "building", x: 110, y: 14, label: "barn" },
        { kind: "tag", x: 20, y: 34, label: "on the road map" },
        { kind: "route", x1: 60, y1: 98, x2: 120, y2: 64, label: "fences?", unknown: true },
      ],
      caption: "The barn has a public address. Whether fences stop visitors was not confirmed.",
    },
    proposed: {
      items: [
        { kind: "road", y: 100, label: "public road" },
        { kind: "building", x: 110, y: 14, label: "barn" },
        { kind: "tag", x: 20, y: 34, label: "farm lane only" },
      ],
      caption: "Reached only from inside the farm.",
    },
  },
  "entrance-check": {
    plans: {
      items: [
        { kind: "road", y: 100, label: "customers' road" },
        { kind: "building", x: 110, y: 10, label: "shop" },
        { kind: "gate", x: 60, y: 50, label: "customer entrance" },
      ],
      caption: "Customers come through the entrance. No checkpoint is in the plans.",
    },
    proposed: {
      items: [
        { kind: "road", y: 100, label: "customers' road" },
        { kind: "building", x: 110, y: 10, label: "shop" },
        { kind: "check", x: 60, y: 50, label: "checkpoint here only" },
      ],
      caption: "Requests screened at this entrance. Other ways in are not covered.",
    },
  },
  logbook: {
    plans: {
      items: [
        { kind: "gate", x: 30, y: 40, label: "gate" },
        { kind: "book", x: 120, y: 40, label: "logbook?", unknown: true },
      ],
      caption: "No logbook in the plans. One may be kept elsewhere; confirm first.",
    },
    proposed: {
      items: [
        { kind: "gate", x: 30, y: 40, label: "gate" },
        { kind: "book", x: 120, y: 40, label: "logbook" },
      ],
      caption: "A record of who came through. It records; it does not block.",
    },
  },
  "sealed-logbook": {
    plans: {
      items: [{ kind: "book", x: 75, y: 30, label: "seal not shown", unknown: true }],
      caption: "No seal shown in the plans. If there is none, a changed page might go unnoticed.",
    },
    proposed: {
      items: [{ kind: "book", x: 75, y: 30, label: "sealed pages", sealed: true }],
      caption: "Changes to the pages would show.",
    },
  },
  "key-list": {
    plans: {
      items: [
        { kind: "building", x: 110, y: 14, label: "farm" },
        { kind: "tag", x: 14, y: 50, label: "keys: broad" },
      ],
      caption: "The key list covers far more than one job needs. Other rules may still limit it.",
    },
    proposed: {
      items: [
        { kind: "building", x: 110, y: 14, label: "farm" },
        { kind: "tag", x: 14, y: 50, label: "keys: named rooms" },
      ],
      caption: "The list names only the rooms needed.",
    },
  },
  "standby-barn": {
    plans: {
      items: [{ kind: "building", x: 30, y: 24, label: "field A" }],
      caption: "Only one place shown in the plans.",
    },
    proposed: {
      items: [
        { kind: "building", x: 14, y: 24, label: "field A" },
        { kind: "building", x: 110, y: 24, label: "field B (standby)" },
      ],
      caption: "A second place can take over. It copies mistakes too; it is not a backup.",
    },
  },
  "dated-copies": {
    plans: {
      items: [{ kind: "book", x: 75, y: 30, label: "dated copies not shown", unknown: true }],
      caption: "The plans show no earlier versions kept, or only a day's worth.",
    },
    proposed: {
      items: [{ kind: "stack", x: 65, y: 26, label: "dated copies" }],
      caption: "Earlier versions kept for a set time.",
    },
  },
  "removal-interlock": {
    plans: {
      items: [
        { kind: "building", x: 20, y: 24, label: "barn" },
        { kind: "tag", x: 110, y: 50, label: "remove switch" },
      ],
      caption:
        "No interlock shown in the plans. If there is none, one mistaken switch could remove the barn.",
    },
    proposed: {
      items: [
        { kind: "building", x: 20, y: 24, label: "barn" },
        { kind: "check", x: 110, y: 40, label: "interlock" },
      ],
      caption: "Removal becomes deliberate. Not a spare barn.",
    },
  },
  "order-intake": {
    plans: {
      items: [
        { kind: "stack", x: 20, y: 26, label: "orders" },
        { kind: "building", x: 120, y: 24, label: "no own limit" },
      ],
      caption: "Orders are taken as they come, up to the county-wide cap only.",
    },
    proposed: {
      items: [
        { kind: "stack", x: 20, y: 26, label: "orders" },
        { kind: "check", x: 120, y: 34, label: "limit" },
      ],
      caption: "A set number at a time; the rest wait or are turned away.",
    },
  },
  "failed-tray": {
    plans: {
      items: [{ kind: "tag", x: 40, y: 50, label: "failed tray: emptied early" }],
      caption: "Failed orders can expire before anyone checks.",
    },
    proposed: {
      items: [{ kind: "tag", x: 40, y: 50, label: "failed tray: kept longer" }],
      caption: "Kept long enough to check. Someone still has to look.",
    },
  },
  "sealed-records": {
    plans: {
      items: [{ kind: "book", x: 75, y: 30, label: "seal not shown", unknown: true }],
      caption: "No seal shown in the plans. If there is none, a copy taken away could be read.",
    },
    proposed: {
      items: [{ kind: "book", x: 75, y: 30, label: "sealed cabinet", sealed: true }],
      caption: "Copies are unreadable. People allowed at the desk can still read.",
    },
  },
  "covered-transport": {
    plans: {
      items: [
        { kind: "building", x: 10, y: 24, label: "barn" },
        { kind: "building", x: 130, y: 24, label: "office" },
        { kind: "route", x1: 70, y1: 50, x2: 130, y2: 50, label: "open cart" },
      ],
      caption: "Records travel uncovered.",
    },
    proposed: {
      items: [
        { kind: "building", x: 10, y: 24, label: "barn" },
        { kind: "building", x: 130, y: 24, label: "office" },
        { kind: "route", x1: 70, y1: 50, x2: 130, y2: 50, label: "covered cart" },
      ],
      caption: "Covered on the way. Not a check on who receives them.",
    },
  },
};

export const SCENE_KEYS = Object.keys(SCENES) as SceneKey[];
