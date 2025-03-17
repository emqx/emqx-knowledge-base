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
- Database: SQLite (default), PostgreSQL (optional)
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
- `LLM_API_KEY`: Your LLM API key (or use `OPENAI_API_KEY` for backward compatibility)
- `LLM_MODEL`: The model to use (depends on the provider, default: gpt-4o)
- `LLM_TEMPERATURE`: The temperature to use for generation (default: 0.7)
- `EMBEDDING_MODEL`: The embedding model to use (default: text-embedding-3-small)
- `EMBEDDING_DIMENSION`: The dimension of the embeddings (default: 1536)

### Database
- `DATABASE_URL`: The database URL (default: sqlite:///knowledge_base.db)

### Slack Integration
- `SLACK_BOT_TOKEN`: Your Slack bot token (optional)
- `SLACK_APP_TOKEN`: Your Slack app token (optional)
- `SLACK_SIGNING_SECRET`: Your Slack signing secret (optional)
- `SLACK_TEAM_ID`: Your Slack team ID (optional)

### EMQX Configuration
- `EMQX_BASE_URL`: The base URL for the EMQX API (default: http://localhost:18083/api/v5)
- `EMQX_USR_NAME`: The EMQX username (default: admin)
- `EMQX_PWD`: The EMQX password (default: public)

### Feature Flags
- `ENABLE_SLACK`: Whether to enable Slack integration (default: false)
- `ENABLE_LOG_ANALYSIS`: Whether to enable log analysis (default: true)

## API Endpoints

- `POST /api/ask`: Ask a question to the knowledge base
- `POST /api/analyze-log`: Analyze an EMQX log
- `GET /api/health`: Health check endpoint

## Web UI

The web UI is available at http://localhost:8000 and includes:

- A page for asking questions and getting answers
- A page for analyzing EMQX logs

## Log Analysis

The log analysis feature uses LlamaIndex to analyze EMQX logs and provide troubleshooting recommendations. It can:

- Extract information from EMQX logs
- Identify issues and their potential causes
- Provide step-by-step troubleshooting recommendations

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
