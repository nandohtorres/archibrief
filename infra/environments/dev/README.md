# dev environment

## Custom domain setup

Cloudflare is the DNS host, not Route53, so this environment has no
Terraform-managed DNS resource (and no Cloudflare provider or API token in
this repo); DNS records are added manually in the Cloudflare dashboard.
That makes this a two-phase apply: the ACM certificate can't finish
validating until its DNS records exist, and the certificate has to exist
before Terraform can build the CloudFront/API Gateway resources that
depend on it.

### Step 1 — create the certificate request

```
cd infra/environments/dev
terraform apply -target=aws_acm_certificate.site
```

This only requests the cert (covering `archibrief.dev`,
`www.archibrief.dev`, `api.archibrief.dev`); nothing else in the plan runs.

### Step 2 — add the validation records in Cloudflare

```
terraform output -json acm_validation_records
```

For each of the 3 entries, add a CNAME in the Cloudflare dashboard
using the given `name`/`value`, set to **DNS Only (grey cloud)**. A
proxied (orange cloud) validation record will not validate.

ACM's validation check can take a few minutes after the record is
visible.

### Step 3 — full apply

```
terraform apply
```

This finishes certificate validation, then creates the CloudFront
aliases/custom cert and the API Gateway regional custom domain, which
both depend on the validated certificate.

### Step 4 — point the domain at the infrastructure

```
terraform output frontend_dns_target
terraform output api_dns_target
```

In Cloudflare, add:
- `archibrief.dev` → CNAME → `frontend_dns_target` (Cloudflare supports
  CNAME flattening at the apex)
- `www.archibrief.dev` → CNAME → `frontend_dns_target`
- `api.archibrief.dev` → CNAME → `api_dns_target`

Use **DNS Only (grey cloud)** here too. CloudFront is already a CDN and
terminates TLS with the ACM cert; proxying through Cloudflare adds a
second CDN hop for no benefit and makes it unclear which layer's TLS
config applies. Enabling Cloudflare's proxy (for its WAF or caching) would
be a separate decision.

### Step 5 — point the frontend build at the custom API domain (optional)

`NEXT_PUBLIC_API_BASE_URL` in the frontend's `.env.production.local` can
point at either the raw `https://<id>.execute-api.us-east-1.amazonaws.com`
endpoint or `https://api.archibrief.dev`. Once the custom domain serves
traffic (verify with `curl` first), switch to it and rebuild/redeploy the
frontend (see `infra/modules/frontend-hosting`'s README for the
`aws s3 sync`/`cloudfront create-invalidation` steps). The raw endpoint
keeps working either way.

### Verifying it worked

```
curl -I https://archibrief.dev
curl -I https://api.archibrief.dev
```

Both should return HTTP responses (not a DNS/connection error). Then load
`https://archibrief.dev` in a browser and confirm a review works end to
end, since the CORS (`additional_cors_origins`) and CSP (`connect-src`)
settings for the custom domain can only be tested once it resolves.
