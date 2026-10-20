# Trap (part 2): a second, completely unprotected bucket ALSO named "logs"
# in a different module - the hardened one's controls must not vouch for it.
resource "aws_s3_bucket" "logs" {
  bucket = "acme-legacy-raw-logs"
}
