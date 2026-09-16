output "vector_bucket_name" {
  value = aws_s3vectors_vector_bucket.knowledge_base.vector_bucket_name
}

output "index_name" {
  value = aws_s3vectors_index.knowledge_base.index_name
}
