# Terraform module: s3-vectors
# A rebuildable vector index built on top of infra/modules/s3 — NOT the
# source of truth itself (ADR-0007, ADR-0042). Index dimension, distance
# metric, and non-filterable metadata keys are exposed as required
# variables with no default, since they are immutable after index
# creation — see variables.tf for the reasoning on each.
#
# Requires AWS provider >= 6.24 (s3vectors resources). Verify exact
# argument names against `terraform providers schema` at first `terraform
# init` — this resource type is new (GA'd 2026) and evolved during
# provider development.

resource "aws_s3vectors_vector_bucket" "knowledge_base" {
  vector_bucket_name = var.vector_bucket_name
  tags                = var.tags
}

resource "aws_s3vectors_index" "knowledge_base" {
  vector_bucket_name = aws_s3vectors_vector_bucket.knowledge_base.vector_bucket_name
  index_name          = var.index_name
  data_type           = var.data_type
  dimension           = var.dimension
  distance_metric     = var.distance_metric

  metadata_configuration {
    non_filterable_metadata_keys = var.non_filterable_metadata_keys
  }
}
