#!/usr/bin/env bash
# Builds the static site and publishes it to the frontend bucket behind
# CloudFront.
#
#   FRONTEND_BUCKET=<bucket> DISTRIBUTION_ID=<id> AWS_PROFILE=<profile> \
#     scripts/deploy_frontend.sh
#
# The build reads frontend/.env.production.local for the API origin.
#
# Files under _next/static have a content hash in their name and never
# change, so browsers may keep them for a year. Everything else (HTML,
# demo JSON) has a fixed name and is uploaded without a cache lifetime.
#
# Old hashed files are kept: a page loaded just before the deploy can
# still fetch the chunks it was built with.
set -euo pipefail

: "${FRONTEND_BUCKET:?set FRONTEND_BUCKET}"
: "${DISTRIBUTION_ID:?set DISTRIBUTION_ID}"

cd "$(dirname "$0")/../frontend"
npm run build

aws s3 sync out/_next/static "s3://${FRONTEND_BUCKET}/_next/static" \
  --cache-control "public, max-age=31536000, immutable" --only-show-errors
aws s3 sync out/ "s3://${FRONTEND_BUCKET}/" \
  --delete --exclude "_next/static/*" --only-show-errors

# Without this, Git Bash rewrites "/*" into a Windows path.
MSYS_NO_PATHCONV=1 aws cloudfront create-invalidation \
  --distribution-id "${DISTRIBUTION_ID}" --paths "/*" \
  --query "Invalidation.Id" --output text
