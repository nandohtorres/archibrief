# dev environment

## Custom domain setup (Phase B, drafted 2026-10-14 — not yet applied)

`archibrief.dev` was registered on Cloudflare 2026-09-08 but was never
actually wired to the deployment — confirmed via `nslookup` against two
public resolvers (NS records correctly delegate to Cloudflare, but there
is no A/CNAME record at all) and by reading the Terraform directly (no
DNS resource, no ACM cert, no CloudFront/API Gateway custom-domain
config anywhere). Full story in the private Work-Project-Issues-Log.md,
2026-10-14 entry.

This is drafted and ready to apply, held on standby — same
prepare-and-hold pattern as the IAM permission-set split earlier the
same day. Nothing below has been applied yet.

Cloudflare is the DNS host, not Route53, so this environment has no
Terraform-managed DNS resource (no Cloudflare provider/API token added
either — the DNS side stays a manual step in the Cloudflare dashboard,
not a new credential in this repo). That makes this a real two-phase
apply: the ACM certificate can't finish validating until its DNS
records exist, and the certificate has to exist before Terraform can
build the CloudFront/API Gateway resources that depend on it.

### Step 1 — create the certificate request

```
cd infra/environments/dev
terraform apply -target=aws_acm_certificate.site
```

This only requests the cert (covering `archibrief.dev`,
`www.archibrief.dev`, `api.archibrief.dev`) — nothing else in this
plan runs yet.

### Step 2 — add the validation records in Cloudflare

```
terraform output -json acm_validation_records
```

For each of the 3 entries, add a CNAME in the Cloudflare dashboard
using the given `name`/`value`, set to **DNS Only (grey cloud)** — a
proxied (orange cloud) validation record will not validate.

Wait a few minutes for DNS to propagate (Cloudflare is typically fast,
but ACM's own validation check can still take a few minutes after the
record is visible).

### Step 3 — full apply

```
terraform apply
```

This finishes certificate validation, then creates the CloudFront
aliases/custom cert and the API Gateway regional custom domain, which
both depend on the now-validated certificate.

### Step 4 — point the domain at the real infrastructure

```
terraform output frontend_dns_target
terraform output api_dns_target
```

In Cloudflare, add:
- `archibrief.dev` → CNAME → `frontend_dns_target` (Cloudflare supports
  CNAME flattening at the apex — most registrars don't, this one does)
- `www.archibrief.dev` → CNAME → `frontend_dns_target`
- `api.archibrief.dev` → CNAME → `api_dns_target`

Same **DNS Only (grey cloud)** note as step 2 — CloudFront is already
a CDN/edge network and already terminates TLS with the ACM cert from
this apply; proxying through Cloudflare on top adds a second CDN hop
for no benefit and complicates which layer's TLS config actually
matters. If Cloudflare's proxy (orange cloud) is wanted later for its
own reasons (WAF, additional caching), that's a deliberate separate
decision, not the default here.

### Step 5 — point the frontend build at the custom API domain (optional)

The frontend's `.env.production.local` currently points
`NEXT_PUBLIC_API_BASE_URL` at the raw
`https://<id>.execute-api.us-east-1.amazonaws.com` endpoint. Once
`api.archibrief.dev` resolves and serves traffic correctly (verify with
`curl` first), update that file to use the custom domain instead and
rebuild/redeploy the frontend (see `infra/modules/frontend-hosting`'s
own README for the `aws s3 sync`/`cloudfront create-invalidation`
steps). Not required for the custom domain to work — the raw endpoint
keeps working either way — but it's the more presentable URL to ship
in anything public-facing (README, demo links, sharing).

### Verifying it worked

```
curl -I https://archibrief.dev
curl -I https://api.archibrief.dev
```

Both should return real HTTP responses (not a DNS/connection error).
Then load `https://archibrief.dev` in a real browser and confirm the
live-API path still works end-to-end — the CORS and CSP changes this
same pass made (`additional_cors_origins`, the frontend's
`connect-src`) both need the custom domain actually resolving to be
testable for real, not just reviewed by reading the Terraform.
