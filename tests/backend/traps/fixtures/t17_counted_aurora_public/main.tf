# Trap: publicly accessible Aurora instances created with count. Trivy
# reports them as name[0], name[1], which the Scan step used to drop
# (found on FEC's public Terraform, 2026-10-15).
resource "aws_rds_cluster" "main" {
  cluster_identifier = "main"
  engine             = "aurora-postgresql"
  storage_encrypted  = true
}

resource "aws_rds_cluster_instance" "main_inst" {
  count               = 2
  cluster_identifier  = aws_rds_cluster.main.id
  instance_class      = "db.r6g.large"
  engine              = "aurora-postgresql"
  publicly_accessible = true
}
