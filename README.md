# EMQX Knowledge Base Slack Bot

A Slack bot that collects problems and solutions from Slack threads and responds to user questions using OpenAI and vector embeddings.

## Features

- **Knowledge Collection**: Users can explicitly request to save valuable Slack threads to the knowledge base
- **Question Answering**: Users can ask questions and get responses based on the collected knowledge
- **Vector Search**: Uses PostgreSQL with pg_vector for efficient similarity search
- **OpenAI Integration**: Leverages OpenAI's Response API for generating high-quality answers

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL with pg_vector extension
- Slack App with appropriate permissions
- OpenAI API key

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/emqx-knowledge-base.git
   cd emqx-knowledge-base
   ```

2. Set up a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e .
   ```

4. Create a `.env` file based on `.env.example` and fill in your credentials.

5. Set up the PostgreSQL database with pg_vector:
   ```bash
   # Start PostgreSQL with Docker (optional)
   docker-compose up -d
   
   # Initialize the database
   python scripts/init_db.py
   ```

### Slack App Configuration

1. Create a new Slack App at https://api.slack.com/apps
2. Add the following Bot Token Scopes:
   - `app_mentions:read`
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `reactions:read`
   - `reactions:write`
3. Enable Socket Mode and Event Subscriptions
4. Subscribe to the following events:
   - `app_mention`
   - `message.channels`
   - `reaction_added`
5. Install the app to your workspace

## Usage

### Starting the Bot

```bash
python main.py
```

### Saving Knowledge

To save a thread to the knowledge base, add a reaction with the 📚 (books) emoji to any message in the thread.

Alternatively, mention the bot with the command:
```
@KnowledgeBot save this thread
```

### Asking Questions

To ask a question, mention the bot:
```
@KnowledgeBot What's the solution for [your question here]?
```

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

### Code Formatting

```bash
black .
isort .
```

## License

MIT
