# frontend-hosting

Phase A static hosting for `frontend/out` (S3 + CloudFront via OAC, default
`*.cloudfront.net` domain). Phase B (custom domain) is a separate, later
step — not built here.

This module only provisions infrastructure. After `terraform apply`,
upload the static export manually:

```
cd frontend
npm run build
aws s3 sync out/ s3://<bucket_id output>/ --delete
aws cloudfront create-invalidation --distribution-id <cloudfront_distribution_id output> --paths "/*"
```

The invalidation matters for `index.html`/`404.html`/`index.txt` even
though they're set to `CachingDisabled` at the CloudFront cache-policy
level — browsers and any intermediate cache may still hold a stale copy
until you've confirmed otherwise; cheap to always invalidate on deploy.
