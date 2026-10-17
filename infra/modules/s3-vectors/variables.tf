variable "vector_bucket_name" {
  type        = string
  description = "Name of the S3 Vectors bucket."
}

variable "index_name" {
  type        = string
  description = "Name of the S3 Vectors index."
}

# No default on purpose: dimension is immutable after index creation
# (ADR-0007/0042), and changing it means a new index. Titan V2 embeds at
# 1024 dimensions (ADR-0035).
variable "dimension" {
  type        = number
  description = "Vector dimension — immutable after index creation. Must match the embedding model's output size exactly."
}

# cosine | euclidean — immutable after index creation.
variable "distance_metric" {
  type        = string
  description = "Distance metric for similarity search — immutable after index creation."

  validation {
    condition     = contains(["cosine", "euclidean"], var.distance_metric)
    error_message = "distance_metric must be \"cosine\" or \"euclidean\"."
  }
}

# Immutable after index creation (ADR-0007/0042), chosen for the
# citation metadata set (ADR-0027, ADR-0036). The keys
# listed here are excluded from the filterable metadata size limit, but
# also excluded from metadata-based query filtering.
variable "non_filterable_metadata_keys" {
  type        = list(string)
  description = "Metadata keys excluded from filtering — immutable after index creation."
  default     = ["exact_text_span", "text"]
}

variable "data_type" {
  type    = string
  default = "float32"
}

variable "tags" {
  type    = map(string)
  default = {}
}
