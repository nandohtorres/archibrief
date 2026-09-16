output "ci_deploy_role_arn" {
  value = try(aws_iam_role.ci_deploy[0].arn, null)
}

output "admin_break_glass_group_name" {
  value = aws_iam_group.admin_break_glass.name
}

output "runtime_permissions_boundary_arn" {
  value = aws_iam_policy.runtime_permissions_boundary.arn
}
