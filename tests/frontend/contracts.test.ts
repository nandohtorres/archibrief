import { isSubmitReviewResponse } from "../../frontend/lib/contracts";

describe("submit-review response guard", () => {
  it.each(["pending", "needs_clarification", "complete"])(
    "accepts the deployed %s response shape",
    (status) => {
      expect(isSubmitReviewResponse({ reviewId: "review-123", status })).toBe(
        true,
      );
    },
  );

  it.each([
    null,
    {},
    { review_id: "review-123", status: "pending" },
    { reviewId: "review-123", status: "failed" },
    { reviewId: 123, status: "pending" },
  ])("rejects unsupported or malformed responses", (candidate) => {
    expect(isSubmitReviewResponse(candidate)).toBe(false);
  });
});
