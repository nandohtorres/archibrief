import type { RecentReview } from "@/lib/review-access";

interface RecentReviewsProps {
  reviews: RecentReview[];
  onOpen: (reviewId: string) => void;
}

function submitted(at: number): string {
  return new Date(at).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// This browser's reviews that can still be opened. Opening one reads the
// saved report; it never starts a new paid review.
export function RecentReviews({ reviews, onOpen }: RecentReviewsProps) {
  if (reviews.length === 0) return null;
  return (
    <section className="recent-reviews" aria-labelledby="recent-reviews-heading">
      <div className="recent-reviews-heading">
        <h2 id="recent-reviews-heading">Your recent reviews</h2>
        <p>Saved in this browser for 7 days after each review starts.</p>
      </div>
      <ul>
        {reviews.map((review) => (
          <li key={review.reviewId}>
            <span className="recent-review-name">
              <strong>{review.label || "Untitled review"}</strong>
              <span>Submitted {submitted(review.submittedAt)}</span>
            </span>
            <button
              className="button secondary"
              type="button"
              aria-label={`Open ${review.label || "untitled review"}`}
              onClick={() => onOpen(review.reviewId)}
            >
              Open
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
