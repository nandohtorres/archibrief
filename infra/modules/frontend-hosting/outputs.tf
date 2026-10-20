output "cloudfront_domain_name" {
  description = "Default *.cloudfront.net domain. Always served, including when var.aliases adds custom domains; the API's CORS frontend_origin must list whichever origin visitors actually use."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "Needed for cache invalidation after a deploy (aws cloudfront create-invalidation)."
  value       = aws_cloudfront_distribution.frontend.id
}

output "bucket_id" {
  value = aws_s3_bucket.frontend.id
}
