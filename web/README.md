# EMQX Knowledge Base Web UI

This is the web interface for the EMQX Knowledge Base application. It allows users to ask questions and get answers from the knowledge base.

## Development Setup

### Prerequisites

- Node.js 18 or later
- npm or yarn

### Technologies Used

- Vue.js 3 - Progressive JavaScript framework
- Vue Router - Official router for Vue.js
- Tailwind CSS v4 - Utility-first CSS framework
- Vite - Next generation frontend tooling

### Installation

1. Install dependencies:

```bash
npm install
```

2. Start the development server:

```bash
npm run dev
```

The application will be available at http://localhost:5173.

### Connecting to the Backend

The web UI needs to connect to the backend API. There are two ways to do this:

#### Option 1: Using the Deployed Backend

If you want to use the backend deployed in AWS, you need to set up port forwarding using AWS SSM:

```bash
aws ssm start-session \
  --target $(aws ec2 describe-instances --filters "Name=tag:Name,Values=emqx-knowledge-base-prod" --query "Reservations[0].Instances[0].InstanceId" --output text) \
  --document-name AWS-StartPortForwardingSession \
  --parameters "localPortNumber=3000,portNumber=3000"
```

This will forward your local port 3000 to port 3000 on the EC2 instance, allowing the web UI to communicate with the backend.

#### Option 2: Running the Backend Locally

If you want to run the backend locally, follow the instructions in the main README file.

## Building for Production

To build the application for production:

```bash
npm run build
```

This will create a `dist` directory with the compiled assets.

## Deployment

The web UI can be deployed to AWS using the Terraform configuration in the `infra` directory. The configuration will:

1. Create an S3 bucket to host the web UI
2. Set up CloudFront for content delivery
3. Configure Lambda@Edge for authentication (if enabled)

To deploy the web UI:

1. Build the application:

```bash
npm run build
```

2. Apply the Terraform configuration:

```bash
cd ../infra
terraform apply
```

3. Upload the built files to the S3 bucket:

```bash
aws s3 sync ../web/dist s3://emqx-knowledge-base-prod-web
```
