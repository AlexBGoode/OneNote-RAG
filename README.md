# OneNote RAG Application

Microsoft OneNote API integration with Refresh Token persistence.

## Development (PyCharm + Docker)

1. First time: Run `python auth.py` locally (follows device flow)
2. Token saved to: `~/.onenote_rag/refresh_token`
3. Docker automatically uses the same token via volume mount

## Docker Quick Start

```bash
# Build and run
docker-compose up --build

# The container automatically uses your existing token
# New tokens are saved back to ~/.onenote_rag/refresh_token
