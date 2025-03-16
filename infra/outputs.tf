output "instance_id" {
  description = "ID of the EC2 instance"
  value       = aws_instance.app.id
}

output "instance_private_ip" {
  description = "Private IP address of the EC2 instance"
  value       = aws_instance.app.private_ip
}

output "db_host" {
  description = "Hostname of the database"
  value       = aws_db_instance.main.address
}

output "db_port" {
  description = "Port of the database"
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "Name of the database"
  value       = aws_db_instance.main.db_name
}

output "db_secret_arn" {
  description = "The ARN of the secret containing the master user password"
  value       = aws_db_instance.main.master_user_secret.0.secret_arn
}

output "db_instance_identifier" {
  description = "The RDS instance identifier"
  value       = aws_db_instance.main.id
}

output "get_password_command" {
  description = "Command to retrieve the database password"
  value       = "aws --region ${var.aws_region} secretsmanager get-secret-value --secret-id '${aws_db_instance.main.master_user_secret[0].secret_arn}' --query 'SecretString' --output text | jq -r .password"
} 
