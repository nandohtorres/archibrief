output "cloudfront_domain_name" {
  description = "Default *.cloudfront.net domain — the actual URL to visit until Phase B (custom domain) lands."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "Needed for cache invalidation after a deploy (aws cloudfront create-invalidation)."
  value       = aws_cloudfront_distribution.frontend.id
}

output "bucket_id" {
  value = aws_s3_bucket.frontend.id
}
