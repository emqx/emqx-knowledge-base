# EMQX Knowledge Base Infrastructure

This directory contains the Terraform configuration for deploying the EMQX Knowledge Base application to AWS.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform installed (version >= 1.2.0)
- An AWS account with permissions to create:
  - EC2 instances
  - RDS instances
  - S3 buckets
  - IAM roles and policies
  - Security groups
  - SSM access

## Configuration

1. Copy the example variables file:
```bash
cp terraform.tfvars.example terraform.tfvars
```

2. Edit `terraform.tfvars` with your configuration:
- Set your desired AWS region
- Configure instance types
- Set database credentials
- Add Slack API tokens
- Add OpenAI API key

## Deployment

1. Initialize Terraform:
```bash
terraform init
```

2. Review the deployment plan:
```bash
terraform plan
```

3. Apply the configuration:
```bash
terraform apply
```

## Managing the Application

The application is deployed without SSH access for security reasons. All management is done through AWS Systems Manager (SSM).

### Viewing Application Logs

```bash
# Get the instance ID
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=emqx-knowledge-base-prod" \
  --query 'Reservations[].Instances[?State.Name==`running`][].InstanceId' \
  --output text

# View systemd service logs
aws ssm send-command \
  --instance-ids "i-1234567890abcdef0" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["journalctl -u emqx-knowledge-base -n 100 --no-pager"]'
```

### Restarting the Service

```bash
aws ssm send-command \
  --instance-ids "i-1234567890abcdef0" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl restart emqx-knowledge-base"]'
```

### Updating Application Code

The application code is stored in an S3 bucket and is automatically deployed during instance creation. To update the code:

1. Make your changes to the application code
2. Run `terraform apply` to package and upload the new code
   - This will create a new zip file
   - Upload it to S3
   - Trigger an instance replacement due to user data changes

For quick updates without instance replacement:

```bash
# Package the code
cd /path/to/your/code
zip -r app.zip . -x "*.git*" -x "infra/*" -x "__pycache__/*" -x "*.pyc" -x ".env"

# Upload to S3
aws s3 cp app.zip s3://emqx-knowledge-base-prod-code/latest.zip

# Restart the service
aws ssm send-command \
  --instance-ids "i-1234567890abcdef0" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["cd /opt/emqx-knowledge-base && sudo -u admin aws s3 cp s3://emqx-knowledge-base-prod-code/latest.zip code.zip && sudo -u admin unzip -o code.zip && systemctl restart emqx-knowledge-base"]'
```

### Starting an SSM Session

To get an interactive shell:

```bash
aws ssm start-session --target i-1234567890abcdef0
```

### Checking Service Status

```bash
aws ssm send-command \
  --instance-ids "i-1234567890abcdef0" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl status emqx-knowledge-base"]'
```

## Infrastructure Updates

To update the infrastructure:

1. Modify the Terraform configuration files
2. Run `terraform plan` to review changes
3. Run `terraform apply` to apply changes

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Note**: This will delete all resources including the database. Make sure to backup any important data before destroying the infrastructure.

## Security Notes

- The EC2 instance is managed via SSM instead of SSH for enhanced security
- Database credentials and API keys are marked as sensitive in Terraform
- Security groups are configured to allow minimum required access
- All sensitive environment variables are passed through systemd service configuration 