import { LOADING_FACTS } from "../../frontend/lib/facts";

test("loading facts are unique, short sentences", () => {
  expect(LOADING_FACTS.length).toBeGreaterThanOrEqual(20);
  expect(new Set(LOADING_FACTS).size).toBe(LOADING_FACTS.length);
  for (const fact of LOADING_FACTS) {
    expect(fact.length).toBeLessThanOrEqual(140);
    expect(fact).toMatch(/[.!]$/);
  }
});
