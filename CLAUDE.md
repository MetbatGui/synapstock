# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Evenezer** — a Korean stock market mindmap orchestrator that connects news and stocks. It manages board layouts (via Miro), syncs data with Google Drive, scrapes KRX (Korean Exchange) market data, and exposes everything through a FastAPI web UI and a Telegram bot.

## Commands

```bash
# Run the web server (port 8090)
uv run evenezer

# Run the Telegram bot
uv run evenezer-bot

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

**Domain** (`src/evenezer/domain/`) — Core business entities (`Stock`, `Node`, `Board`) and abstract ports (`ports.py`). No external dependencies. Sub-domains for `news/`, `statistics/`, `financials/`, `heatmap/`, `analytics/`.

**Application** (`src/evenezer/application/services/`) — 18 service modules orchestrating use cases. Key services:
- `BoardCommandService` / `BoardQueryService` — CRUD on boards
- `BoardFileSyncService` — syncs boards with Google Drive
- `StatisticsService` — market stats (net-buy, ceiling, bonus issue, etc.)
- `HeatmapService` — theme-based heatmap generation
- `NewsService` — scrapes and archives news per stock

**Infrastructure** (`src/evenezer/infrastructure/`) — Concrete adapters behind domain ports:
- `adapters/google/` — Google Drive upload/download
- `adapters/krx/` — KRX API (market data, KRX login)
- `adapters/miro/` — Miro REST API (board manipulation)
- `adapters/scraper/` — Naver/web scraping via httpx + BeautifulSoup
- `adapters/disclosure/` — DART (financial disclosure) API
- `adapters/financial/` — Excel financial statement parsing
- `adapters/local/` — Local JSON/file repositories
- `persistence/` — Repository implementations

All services are wired together in `infrastructure/container.py` — a single `container` singleton used for dependency injection across the app.

**Presentation** (`src/evenezer/presentation/`) — Two channels:
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

## Development Methodology

### 1. 브랜치 네이밍 컨벤션 및 깃 워크플로우 (Branch Strategy & Git Workflow)
작업의 성격에 따라 아래 5가지 접두사를 명확히 구분하여 사용합니다.
- `feature/`: 새로운 기능 개발
- `fix/`: 버그 수정
- `refactor/`: 기능 변화 없는 코드 구조/성능 개선
- `chore/`: 빌드, 패키지 매니저, CI/CD 등 설정 변경
- `hotfix/`: 운영 환경의 치명적인 버그 긴급 수정

**깃 워크플로우 운영 규칙**:

> [!IMPORTANT]
> **핵심 깃 워크플로우 강제 규칙**:
> 1. 이슈로 정의할 만한 의미 있는 작업(기능 개발, 버그 수정 등)에 대해 **무조건 새로운 브랜치를 생성**하여 작업합니다. (단, 매우 사소한 오타 수정이나 단순 문서 보완 등은 예외로 할 수 있습니다.)
> 2. 로컬 브랜치에서 작업하는 과정에서 변경 사항을 항상 **원격 저장소에 Push**합니다.
> 3. 작업이 끝나면 `master` 브랜치로 전환 후 **`git merge --no-ff <branch_name>`** 옵션을 사용하여 병합함으로써 명시적인 병합 흔적(Merge Commit)을 남깁니다.
> 4. 병합 시 생성되는 **Merge Commit 메시지는 Pull Request(PR) 리포트처럼 상세히 작성**하여 브랜치 작업 리포트로 활용합니다.

- **브랜치 기반 개발**: 어떠한 작업(단순 문서 수정 포함)이든 `master` 브랜치에서 직접 개발하거나 커밋하지 않으며, 항상 목적에 부합하는 브랜치를 생성하여 작업합니다.
- **원격 반영 (Push)**: 로컬 브랜치에서 작업하는 과정에서 항상 변경 사항을 원격 저장소에 push합니다.
- **비-속도전진 병합 (Non-Fast-Forward Merge)**:
  - 작업이 끝난 브랜치를 `master` 브랜치에 병합할 때는 반드시 `git merge --no-ff <branch_name>` 옵션을 사용합니다.
  - 이는 Fast-forward를 방지하여 명시적인 병합 커밋(Merge Commit)의 흔적을 남기기 위함입니다.
- **병합 커밋의 PR 리포트화**:
  - `--no-ff` 병합 시 생성되는 병합 커밋 메시지를 마치 Pull Request(PR) 리포트처럼 상세히 작성합니다.
  - 해당 병합 커밋 메시지에는 이 브랜치에서 수행된 구체적인 변경 사항 요약, 설계 결정, 검증 결과를 포함하여 히스토리를 완벽하게 문서화해야 합니다.



### 2. 이상적인 문제 해결 워크플로우 (TDD & Integration Loop)
작업의 성격(신규 기능 개발 vs 버그 수정)에 따라 워크플로우를 다르게 적용합니다. feat/와 fix/는 문제 접근 방식이 다릅니다.

#### A. 신규 기능 개발 워크플로우 (feature/)
복잡한 문제를 작게 나누고, 안전망(통합 테스트)을 쳐둔 상태에서 핵심 로직을 하나씩 완성해 나가는 탑다운-바텀업 혼합 과정입니다.

##### Phase 1: 문제 분할 및 뼈대 구축 (Top-Down)
- **단일 문제 격리**: 여러 문제가 얽혀 있더라도, 한 번에 단 하나의 문제만 목표로 설정합니다.
- **모듈 분할**: 해결해야 할 문제를 구현 가능한 가장 작은 단위(함수, 클래스 등)로 잘게 쪼겹니다.
- **통합 테스트 & 스텁(Stub) 작성**:
  - 쪼개진 작은 단위들이 최종적으로 어떻게 연결될지 청사진 역할을 하는 '통합 테스트'를 먼저 작성합니다.
  - 실제 구현 코드가 없으므로, 모든 작은 단위들은 항상 성공(True)하거나 임시 결괏값을 반환하는 스텁(가짜 모듈)으로 채워 넣습니다.

##### Phase 2: 마이크로 TDD 및 구현 루프 (Bottom-Up)
작게 쪼개둔 각각의 단위 모듈에 대해 아래의 루프를 반복합니다.
1. **🔴 실패하는 테스트 (Red)**: 스텁을 대체할 실제 기능에 대한 구체적인 단위 테스트를 작성합니다. (구현 코드가 없으므로 당연히 실패합니다).
2. **🟢 성공 구현 (Green)**: 방금 작성한 테스트를 통과할 수 있도록 최소한의 실제 코드를 작성합니다.
3. **🔵 리팩토링 (Refactor)**: 기능은 유지한 채, 코드의 가독성, 효율성, 구조를 개선합니다.
4. **🧹 정적 분석 (Linting)**: Ruff 등 린터와 포매터, 타입 체커를 돌려 코드 컨벤션과 타입 안정성을 꼼꼼하게 확보합니다.
5. **🔗 스텁 교체 및 통합 검증**: Phase 1에서 통합 테스트에 꽂아두었던 가짜 스텁을 방금 완성한 실제 코드로 교체합니다. 통합 테스트를 실행하여 파이프라인이 깨지지 않았는지 확인합니다.

##### Phase 3: 완성
- **루프 반복**: 모든 가짜 스텁이 견고하게 테스트된 실제 코드로 교체될 때까지 Phase 2의 루프를 반복합니다.

#### B. 버그 수정 워크플로우 (fix/)
이미 존재하는 코드의 오동작을 바로잡는 과정으로, 스텁 작성 대신 **실패하는 재현 테스트**를 먼저 만드는 바텀업 과정입니다.

##### Phase 1: 버그 재현 및 격리 (Red)
- **재현 테스트 작성**: 보고되거나 발견된 버그 현상을 그대로 재현할 수 있는 단위 테스트 또는 통합 테스트를 가장 먼저 작성합니다.
- **테스트 실패 확인**: 작성한 테스트가 기대와 다르게 실패(Red)하는 것을 확인하여 버그가 발생하는 지점을 정확히 격리합니다.

##### Phase 2: 버그 수정 및 정합성 검증 (Green)
- **최소 코드 수정**: 재현 테스트를 통과(Green)하도록 타겟 소스 코드를 최소한으로 수정합니다. 
- **단위 테스트 통과**: 버그가 말끔히 해결되어 작성한 재현 테스트가 정상 통과하는지 확인합니다.

##### Phase 3: 리팩토링 및 회귀 방지 (Refactor & Regression Test)
- **리팩토링 (Refactor)**: 수정한 코드가 전체 시스템의 가독성이나 성능을 해치지 않는지 검토하고 다듬습니다.
- **회귀 검증**: 해당 버그 수정으로 인해 다른 기존 기능이 깨지지 않았는지 전체 단위/통합 테스트를 실행하여 회귀(Regression) 여부를 최종 검증합니다.


