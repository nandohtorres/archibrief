# Terraform module: frontend-hosting
# S3 + CloudFront static hosting for frontend/out (Next.js static export,
# ADR-0016). Reachable at CloudFront's default *.cloudfront.net domain
# and optionally at custom domains via var.aliases + var.certificate_arn
# (an ACM cert in us-east-1). Both default to off, which keeps the
# default certificate and domain.
#
# The bucket is private; CloudFront reaches it only via Origin Access
# Control (OAC), not the older OAI or a public bucket policy. This module
# does not upload frontend/out's contents — see the module README for the
# `aws s3 sync` command to run manually after `terraform apply`.
#
# `frontend/out` is per-route static HTML from the app router's static
# export, not a single SPA index: unhashed files at the root (index.html,
# 404.html, index.txt RSC payloads) plus content-hashed, immutable assets
# under _next/static/. That split drives the two cache behaviors below:
# unhashed root files are never edge-cached, hashed assets are cached
# aggressively.

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
# injects an inline hydration bootstrap script and there is no server to
# mint per-request CSP nonces; the policy still blocks third-party
# script/iframe injection, the real XSS/clickjacking exposure.
# connect-src allows the API Gateway origin as a wildcard
# *.execute-api.<region>.amazonaws.com pattern rather than the literal
# api_id, which would create a circular module dependency (api_gateway
# depends on this module's cloudfront_domain_name for CORS). It also
# allows the S3 global endpoint (*.s3.amazonaws.com), because ADR-0045's
# direct-upload flow has the browser POST the archive straight to a
# presigned S3 URL. style-src/font-src allow Google Fonts
# (app/globals.css's @import).
resource "aws_cloudfront_response_headers_policy" "frontend_security" {
  name = "${var.name_prefix}-frontend-security-headers"

  security_headers_config {
    content_security_policy {
      override                = true
      content_security_policy = "default-src 'self'; script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' https://challenges.cloudflare.com ${var.api_origin_pattern} https://*.s3.amazonaws.com; frame-src https://challenges.cloudflare.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
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
  aliases             = var.aliases

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # Default behavior covers index.html, 404.html, and any other unhashed
  # per-route HTML/RSC file the app router's static export produces at
  # the root. None of those have a content hash in their filename, so
  # they must not be edge-cached.
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
  # therefore immutable, so it is safe to cache hard.
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
  # own .html file at build time; there is no client-side-only route
  # without a static file, so a 404 is a real 404. Map both
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

  # var.certificate_arn null keeps CloudFront's default certificate, and
  # var.aliases must then be empty; CloudFront enforces that pairing. Set both to serve the custom domain(s).
  viewer_certificate {
    cloudfront_default_certificate = var.certificate_arn == null
    acm_certificate_arn            = var.certificate_arn
    ssl_support_method             = var.certificate_arn == null ? null : "sni-only"
    minimum_protocol_version       = var.certificate_arn == null ? null : "TLSv1.2_2021"
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
  # rather than hand-rolled aws_cloudfront_cache_policy resources for
  # "cache nothing" and "cache hashed assets forever".
  managed_cache_policy_disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # CachingDisabled
  managed_cache_policy_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6" # CachingOptimized
}
