# frontend-hosting

Static hosting for `frontend/out` (S3 + CloudFront via OAC), served at the
default `*.cloudfront.net` domain and optionally at custom domains
(`aliases`/`certificate_arn`). The ACM certificate and its DNS validation
live in `infra/environments/dev/`, because they are shared with the
api-gateway module's custom domain. See that environment's README for the
apply sequence.

This module only provisions infrastructure. After `terraform apply`,
upload the static export manually:

```
cd frontend
npm run build
aws s3 sync out/ s3://<bucket_id output>/ --delete
aws cloudfront create-invalidation --distribution-id <cloudfront_distribution_id output> --paths "/*"
```

Invalidate on every deploy, even though `index.html`/`404.html`/`index.txt`
use the `CachingDisabled` cache policy: browsers and intermediate caches
may still hold a stale copy, and invalidation is cheap.
