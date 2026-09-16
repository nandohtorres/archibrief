# Terraform module: frontend-hosting
# Phase A of the frontend deploy (Work-Project-Deployment-Roadmap.md):
# S3 + CloudFront static hosting for frontend/out (Next.js static export,
# ADR-0016), reachable at CloudFront's default *.cloudfront.net domain.
# No custom domain / ACM cert / alternate domain names yet — that's
# Phase B (archibrief.dev, currently on Cloudflare DNS) and deliberately
# out of scope here.
#
# The bucket is private; CloudFront reaches it only via Origin Access
# Control (OAC), not the older OAI or a public bucket policy. This module
# does not upload frontend/out's contents — see the module README for the
# `aws s3 sync` command to run manually after `terraform apply`.
#
# `frontend/out` (checked against a real `npm run build` during this
# module's implementation, 2026-09-15) is per-route static HTML from the
# app router's static export, not a single SPA index — currently just
# index.html + 404.html + a hashed-filename index.txt (RSC payload) at
# the root, plus content-hashed, effectively-immutable assets under
# _next/static/. That split (hashed vs unhashed) drives the two cache
# behaviors below: unhashed root files must never be edge-cached (no
# invalidation step exists yet — see README), hashed assets can be
# cached aggressively.

resource "aws_s3_bucket" "frontend" {
  bucket = var.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.name_prefix}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# script-src/style-src allow 'unsafe-inline' because Next's static export
# injects an inline hydration bootstrap script and the app has no
# server to mint per-request CSP nonces — still blocks third-party script
#/iframe injection, which is the actual XSS/clickjacking exposure this
# closes. connect-src is 'self'-only since Phase A ships with no live API
# wired; revisit when a real API origin/custom domain exists (Phase B).
resource "aws_cloudfront_response_headers_policy" "frontend_security" {
  name = "${var.name_prefix}-frontend-security-headers"

  security_headers_config {
    content_security_policy {
      override                = true
      content_security_policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    }
    frame_options {
      override     = true
      frame_option = "DENY"
    }
    content_type_options {
      override = true
    }
    referrer_policy {
      override        = true
      referrer_policy = "strict-origin-when-cross-origin"
    }
    strict_transport_security {
      override                   = true
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
    }
  }
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = var.price_class
  comment             = "${var.name_prefix}-frontend"

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Default behavior covers index.html, 404.html, and any other unhashed
  # per-route HTML/RSC file the app router's static export produces at
  # the root — none of those have a content hash in their filename, so
  # they must not be edge-cached (nothing invalidates the edge cache on
  # deploy yet, see README).
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = local.managed_cache_policy_disabled

    response_headers_policy_id = aws_cloudfront_response_headers_policy.frontend_security.id
  }

  # frontend/out/_next/static/** is content-hashed by Next's build and
  # therefore immutable — safe (and the whole point) to cache hard.
  ordered_cache_behavior {
    path_pattern           = "/_next/static/*"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = local.managed_cache_policy_optimized

    response_headers_policy_id = aws_cloudfront_response_headers_policy.frontend_security.id
  }

  # Next static export (app router) prerenders every real route to its
  # own .html file at build time — there's no client-side-only route
  # that's missing a static file, so a true 404 is a real 404. Map both
  # S3's OAC-denied "no such key" (403) and CloudFront's own 404 to the
  # exported 404.html, serving it as an actual 404 rather than faking a
  # 200 SPA fallback.
  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = var.tags
}

resource "aws_s3_bucket_policy" "frontend_cloudfront_access" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_cloudfront_access.json
}

data "aws_iam_policy_document" "frontend_cloudfront_access" {
  statement {
    sid    = "AllowCloudFrontOAC"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

locals {
  origin_id = "${var.name_prefix}-frontend-s3"

  # AWS-managed cache policies (stable IDs, same in every account/region)
  # rather than hand-rolled aws_cloudfront_cache_policy resources — no
  # reason to reinvent "cache nothing" / "cache hashed assets forever".
  managed_cache_policy_disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
  managed_cache_policy_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6" # CachingOptimized
}
