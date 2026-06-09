# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SynapStock** — a Korean stock market mindmap orchestrator that connects news and stocks. It manages board layouts (via Miro), syncs data with Google Drive, scrapes KRX (Korean Exchange) market data, and exposes everything through a FastAPI web UI and a Telegram bot.

## Commands

```bash
# Run the web server (port 8090)
uv run synapstock

# Run the Telegram bot
uv run synapstock-bot

# Run all tests
uv run pytest

# Run only unit tests (no external deps)
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Run a single test file
uv run pytest tests/unit/application/services/test_command_service.py

# Run a single test by name
uv run pytest tests/unit/... -k "test_function_name"

# Lint
uv run ruff check src/

# Type check
uv run mypy src/
```

Line length is 120. Ruff enforces E, F, I, W, UP rule sets. Mypy runs with the Pydantic plugin and excludes the `tests/` directory.

## Architecture

Clean/Hexagonal architecture with four layers:

**Domain** (`src/synapstock/domain/`) — Core business entities (`Stock`, `Node`, `Board`) and abstract ports (`ports.py`). No external dependencies. Sub-domains for `news/`, `statistics/`, `financials/`, `heatmap/`, `analytics/`.

**Application** (`src/synapstock/application/services/`) — 18 service modules orchestrating use cases. Key services:
- `BoardCommandService` / `BoardQueryService` — CRUD on boards
- `BoardFileSyncService` — syncs boards with Google Drive
- `StatisticsService` — market stats (net-buy, ceiling, bonus issue, etc.)
- `HeatmapService` — theme-based heatmap generation
- `NewsService` — scrapes and archives news per stock

**Infrastructure** (`src/synapstock/infrastructure/`) — Concrete adapters behind domain ports:
- `adapters/google/` — Google Drive upload/download
- `adapters/krx/` — KRX API (market data, KRX login)
- `adapters/miro/` — Miro REST API (board manipulation)
- `adapters/scraper/` — Naver/web scraping via httpx + BeautifulSoup
- `adapters/disclosure/` — DART (financial disclosure) API
- `adapters/financial/` — Excel financial statement parsing
- `adapters/local/` — Local JSON/file repositories
- `persistence/` — Repository implementations

All services are wired together in `infrastructure/container.py` — a single `container` singleton used for dependency injection across the app.

**Presentation** (`src/synapstock/presentation/`) — Two channels:
- `web/` — FastAPI app (`server.py`) with Jinja2 templates; routes split by domain (`board`, `stock`, `report`, `statistics`, `financial`, `heatmap`). WebSocket endpoint `/ws/logs` streams real-time logs.
- `telegram/` — python-telegram-bot handlers and conversation flows.

On startup, the web server launches background threads to sync Google Drive indices and news archives.

## Test Structure

Tests are auto-marked by directory:
- `tests/unit/` → `@pytest.mark.unit` — fast, fully isolated
- `tests/integration/` → `@pytest.mark.integration` — may call Google Drive, local files, or real APIs

Test fixtures live in `fixtures/`. Async tests use strict asyncio mode (`asyncio_mode = "strict"` in `pyproject.toml`).

## Data & Configuration

Runtime data is stored under `data/`:
- `data/board/` — board JSON files (synced with Google Drive)
- `data/statistics/{netbuy,ceiling,bonus_issue,weekly_change,stock_split,new_listing}/`
- `data/news/`, `data/report/`, `data/pdf/`, `data/financial_statements/`

Credentials live in `.env` and `secrets/` (Google OAuth tokens). Key env vars: `MIRO_ACCESS_TOKEN`, `TELEGRAM_API_TOKEN`, `GOOGLE_DRIVE_*_FOLDER_ID`, `KRX_USERNAME`/`KRX_PASSWORD`.

The `brain/` module contains Claude/AI integration for analysis tasks. `scripts/` holds batch operations. `scratch/` is experimental code (gitignored).
