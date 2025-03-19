# EMQX Knowledge Base

A knowledge base application for EMQX that allows users to ask questions and get answers based on the knowledge base. It also includes a log analysis feature for EMQX logs.

## Features

- Ask questions and get answers based on the knowledge base
- Upload files to provide additional context for questions
- Analyze EMQX logs to identify issues and get troubleshooting recommendations
- Slack integration for asking questions and getting answers

## Technologies

- Backend: FastAPI, SQLAlchemy, LlamaIndex
- Frontend: Vue.js, Tailwind CSS
- Database: PostgreSQL
- LLM Support: OpenAI, Anthropic, Cohere, Gemini, HuggingFace (via LlamaIndex)

## Setup

1. Clone the repository
2. Install uv (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
4. Edit the `.env` file to set your LLM API key and other configuration options
5. Run the application:
   ```bash
   uv run main.py
   ```

## Environment Variables

### LLM Configuration
- `LLM_PROVIDER`: The LLM provider to use (default: openai, options: openai, anthropic, cohere, gemini, huggingface)
- `LLM_API_KEY`: Your LLM API key
- `LLM_MODEL`: The model to use (depends on the provider, default: gpt-4o)
- `LLM_TEMPERATURE`: The temperature to use for generation (default: 0.7)
- `EMBEDDING_MODEL`: The embedding model to use (default: text-embedding-3-small)
- `EMBEDDING_DIMENSION`: The dimension of the embeddings (default: 1536)

### Database
- `DATABASE_URL`: The database URL (default: postgresql://postgres:postgres@localhost:5432/knowledge_base)

### Slack Integration
- `SLACK_BOT_TOKEN`: Your Slack bot token (optional)
- `SLACK_APP_TOKEN`: Your Slack app token (optional)
- `SLACK_SIGNING_SECRET`: Your Slack signing secret (optional)
- `SLACK_TEAM_ID`: Your Slack team ID (optional)

### Feature Flags
- `ENABLE_SLACK`: Whether to enable Slack integration (default: false)

### Logging and Debugging
- `LOG_LEVEL`: The logging level to use (default: INFO, options: DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LLAMA_INDEX_VERBOSE`: Whether to show verbose LlamaIndex logs, including workflow step execution (default: false)

## API Endpoints

- `GET /api/health`: Health check endpoint

## Web UI

The web UI is available at http://localhost:8000 and includes a unified chat interface that can:

- Answer questions about EMQX Knowledge Base
- Analyze EMQX logs for troubleshooting
- Process file uploads for log analysis
- Handle EMQX API credentials to query broker information

## Development

To set up the development environment:

1. Install frontend dependencies:
   ```bash
   cd web
   npm install
   ```
2. Run the backend:
   ```bash
   uv run main.py
   ```
3. Run the frontend:
   ```bash
   cd web
   npm run dev
   ```

## License

This project is licensed under the MIT License - see the LICENSE file for details.