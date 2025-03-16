data "aws_availability_zones" "available" {}

locals {
  vpc_cidr = "10.0.0.0/16"
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "${var.environment}-vpc"
  cidr = "10.0.0.0/16"

  azs              = local.azs
  private_subnets  = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k)]
  public_subnets   = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 8)]
  database_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 16)]

  create_database_subnet_group       = true
  create_database_subnet_route_table = true
  #create_database_internet_gateway_route = true

  enable_dns_hostnames    = true
  enable_dns_support      = true
  enable_nat_gateway      = false
  map_public_ip_on_launch = true

  tags = {
    Environment = var.environment
  }
}

# Security group for EC2 instance
resource "aws_security_group" "app" {
  name_prefix = "${var.app_name}-app-"
  description = "Security group for ${var.app_name} application"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Security group for RDS
resource "aws_security_group" "db" {
  name_prefix = "${var.app_name}-db-"
  description = "Security group for ${var.app_name} database"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Latest Debian ARM AMI
data "aws_ami" "debian_arm" {
  most_recent = true
  owners      = ["136693071363"] # Debian

  filter {
    name   = "name"
    values = ["debian-12-arm64-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

# Add S3 bucket for code storage
resource "aws_s3_bucket" "app_code" {
  bucket = "${var.app_name}-${var.environment}-code"

  tags = {
    Name = "${var.app_name}-${var.environment}"
  }
}

# Add S3 bucket versioning
resource "aws_s3_bucket_versioning" "app_code" {
  bucket = aws_s3_bucket.app_code.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSM IAM role for EC2
resource "aws_iam_role" "app_role" {
  name = "${var.app_name}-app-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_policy" {
  role       = aws_iam_role.app_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app_profile" {
  name = "${var.app_name}-app-profile"
  role = aws_iam_role.app_role.name
}

# Add IAM policy for S3 access
resource "aws_iam_role_policy" "app_s3_policy" {
  name = "${var.app_name}-s3-policy"
  role = aws_iam_role.app_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.app_code.arn,
          "${aws_s3_bucket.app_code.arn}/*"
        ]
      }
    ]
  })
}

# Create archive of the application code
data "archive_file" "app_code" {
  type        = "zip"
  source_dir  = "${path.root}/../" # Parent directory containing the app code
  output_path = "${path.module}/files/app.zip"
  excludes = [
    ".git",
    ".gitignore",
    ".venv",
    "infra",
    "infra/*",
    ".pytest_cache",
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    ".env",
    ".ruff_cache"
  ]
}

# Upload application code to S3
resource "aws_s3_object" "app_code" {
  bucket = aws_s3_bucket.app_code.id
  key    = "latest.zip"
  source = data.archive_file.app_code.output_path
  etag   = data.archive_file.app_code.output_base64sha256
}

# Store the app code checksum and trigger code update
resource "null_resource" "app_code_update" {
  triggers = {
    code_hash = data.archive_file.app_code.output_base64sha256
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws ssm send-command \
        --region ${var.aws_region} \
        --instance-ids ${aws_instance.app.id} \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=["cd /opt/app && sudo -u app aws s3 cp s3://${aws_s3_bucket.app_code.id}/latest.zip code.zip && sudo -u app unzip -o code.zip && rm code.zip && sudo systemctl restart emqx-knowledge-base"]'
    EOT
  }

  depends_on = [aws_s3_object.app_code]
}

# EC2 instance
resource "aws_instance" "app" {
  ami                    = data.aws_ami.debian_arm.id
  instance_type          = var.instance_type
  subnet_id              = module.vpc.public_subnets[0]
  iam_instance_profile   = aws_iam_instance_profile.app_profile.name
  vpc_security_group_ids = [aws_security_group.app.id]

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = <<-EOF
#!/bin/bash

set -euo pipefail
set -x

# Install required packages
apt-get update
apt-get install -y python3-pip unzip curl jq wget ca-certificates

# Install SSM agent
mkdir -p /tmp/ssm
cd /tmp/ssm
wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_arm64/amazon-ssm-agent.deb
dpkg -i amazon-ssm-agent.deb
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent
cd -
rm -rf /tmp/ssm

# Install posgresql client
apt install -y postgresql-common
install -d /usr/share/postgresql-common/pgdg
curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
apt update
apt install -y postgresql-client-16
PGPASSWORD='${jsondecode(data.aws_secretsmanager_secret_version.db_password.secret_string)["password"]}' psql -h ${aws_db_instance.main.address} -U ${var.db_username} -d ${var.db_name} -c 'CREATE EXTENSION IF NOT EXISTS vector';

# Install uv globally
wget https://github.com/astral-sh/uv/releases/download/0.6.6/uv-aarch64-unknown-linux-gnu.tar.gz
tar xzf uv-aarch64-unknown-linux-gnu.tar.gz
mv uv-aarch64-unknown-linux-gnu/uv /usr/local/bin/
mv uv-aarch64-unknown-linux-gnu/uvx /usr/local/bin/
chmod +x /usr/local/bin/uv
chmod +x /usr/local/bin/uvx

# Create app user with home directory in /opt/app
useradd -m -d /opt/app app
cd /opt/app

# Download and extract application code
sudo -u app aws s3 cp s3://${aws_s3_bucket.app_code.id}/latest.zip code.zip
sudo -u app unzip code.zip
rm code.zip

# Create systemd service
cat > /etc/systemd/system/emqx-knowledge-base.service << 'EOL'
[Unit]
Description=EMQX Knowledge Base
After=network.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/app
Environment=SLACK_BOT_TOKEN=${var.slack_bot_token}
Environment=SLACK_APP_TOKEN=${var.slack_app_token}
Environment=SLACK_SIGNING_SECRET=${var.slack_signing_secret}
Environment=SLACK_TEAM_ID=${var.slack_team_id}
Environment=OPENAI_API_KEY=${var.openai_api_key}
Environment=DATABASE_URL=postgresql://${var.db_username}:${jsondecode(data.aws_secretsmanager_secret_version.db_password.secret_string)["password"]}@${aws_db_instance.main.endpoint}/${var.db_name}
ExecStart=/usr/local/bin/uv run main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOL

# Start and enable the service
systemctl daemon-reload
systemctl enable emqx-knowledge-base
systemctl start emqx-knowledge-base
EOF

  # Add dependency on the code upload
  depends_on = [aws_s3_object.app_code]

  tags = {
    Name = "${var.app_name}-${var.environment}"
  }
}

# RDS instance
resource "aws_db_instance" "main" {
  identifier        = "${var.app_name}-${var.environment}"
  engine            = "postgres"
  engine_version    = "17.2"
  instance_class    = var.db_instance_type
  allocated_storage = 20

  db_name  = var.db_name
  username = var.db_username

  manage_master_user_password = true

  vpc_security_group_ids = [aws_security_group.db.id]
  db_subnet_group_name   = module.vpc.database_subnet_group_name

  backup_retention_period = 7
  skip_final_snapshot    = true

  tags = {
    Name = "${var.app_name}-${var.environment}"
  }
}

data "aws_secretsmanager_secret""db_password" {
  arn = aws_db_instance.main.master_user_secret[0].secret_arn
}

data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = data.aws_secretsmanager_secret.db_password.id
}

# Update the IAM role policy to allow access to RDS-managed secrets
resource "aws_iam_role_policy" "ec2_policy" {
  name = "ec2_policy"
  role = aws_iam_role.app_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = ["arn:aws:secretsmanager:${var.aws_region}:*:secret:rds!db-*"]
      },
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances"
        ]
        Resource = [aws_db_instance.main.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.app_code.arn,
          "${aws_s3_bucket.app_code.arn}/*"
        ]
      }
    ]
  })
}
