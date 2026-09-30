output "node_group_id" {
  description = "ID of the GPU node group"
  value       = aws_eks_node_group.gpu.id
}

output "node_group_arn" {
  description = "ARN of the GPU node group"
  value       = aws_eks_node_group.gpu.arn
}

output "node_group_status" {
  description = "Status of the GPU node group"
  value       = aws_eks_node_group.gpu.status
}
