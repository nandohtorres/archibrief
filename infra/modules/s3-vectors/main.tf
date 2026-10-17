# Terraform module: s3-vectors
# A rebuildable vector index built on top of infra/modules/s3 — NOT the
# source of truth itself (ADR-0007, ADR-0042). Index dimension, distance
# metric, and non-filterable metadata keys are exposed as required
# variables with no default, since they are immutable after index
# creation (see variables.tf for each). Requires AWS provider >= 6.24
# for the s3vectors resources.

resource "aws_s3vectors_vector_bucket" "knowledge_base" {
  vector_bucket_name = var.vector_bucket_name
  tags               = var.tags
}

resource "aws_s3vectors_index" "knowledge_base" {
  vector_bucket_name = aws_s3vectors_vector_bucket.knowledge_base.vector_bucket_name
  index_name         = var.index_name
  data_type          = var.data_type
  dimension          = var.dimension
  distance_metric    = var.distance_metric

  metadata_configuration {
    non_filterable_metadata_keys = var.non_filterable_metadata_keys
  }

  # AWS refuses to edit dimension/distance_metric in place, so Terraform
  # would destroy and recreate the index, silently wiping the embedded
  # corpus. prevent_destroy makes "immutable by decision" (ADR-0007/0042)
  # something Terraform enforces.
  lifecycle {
    prevent_destroy = true
  }
}
