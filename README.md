# Evenezer (이븐에저)

**Evenezer**는 뉴스 데이터와 한국 주식 데이터를 연동하여 주식 시장의 흐름을 마인드맵(Miro)으로 시각화하고 관리하는 통합 마인드맵 오케스트레이터입니다.  
본 문서는 프로젝트의 인수인계 및 원활한 유지보수를 위해 전체적인 시스템 아키텍처, 환경 구성, 실행 방법 및 개발 컨벤션을 상세하게 정리해 둔 문서입니다.

---

## 📌 프로젝트 개요 및 주요 기능

Evenezer는 한국 주식 시장의 테마, 뉴스, 기업 개황 및 재무 공시 등의 방대한 데이터를 가공하여, Miro 보드 상에 마인드맵 형태로 시각화합니다. 사용자는 웹 UI 및 텔레그램 봇을 통해 오케스트레이터를 제어하고 데이터를 관리할 수 있습니다.

### 핵심 기능
- **Miro 보드 연동**: Miro REST API를 활용해 마인드맵 보드 생성, 레이아웃 정렬 및 노드(Node) 상태 업데이트를 자동화합니다.
- **Google Drive 동기화**: Miro 보드 데이터를 로컬 JSON 백업과 동기화하고 Google Drive 저장소로 업로드/다운로드합니다.
- **KRX 시장 데이터 수집**: 한국거래소(KRX)로부터 순매수 추이, 주간 변동, 신규 상장, 무상증자, 주식 분할 등의 통계 데이터를 스크래핑하고 가공합니다.
- **뉴스 아카이빙**: Naver 등 포털 뉴스를 스크래핑(BeautifulSoup, Playwright 활용)하여 주목받는 이슈와 뉴스 데이터를 주식 종목 매칭 키워드 기반으로 아카이빙합니다.
- **시각화 및 관리 인터페이스**:
  - **Web UI (FastAPI)**: 실시간 로그 모니터링(WebSocket), 테마별 히트맵 생성, 보드 관리, 재무 정보 조회가 가능한 대시보드를 제공합니다.
  - **Telegram Bot**: 텔레그램 대화형 인터페이스를 통해 현황을 파악하고 백그라운드 작업을 실행합니다.

---

## 🏗️ 시스템 아키텍처 (Architecture)

Evenezer는 관심사 분리와 점진적 확장을 위해 **클린/헥사고날 아키텍처(Clean/Hexagonal Architecture)** 구조를 채택하고 있습니다. 소스 코드는 크게 4개의 계층으로 구분됩니다.

```
src/evenezer/
├── domain/            # 1. 도메인 계층 (순수 비즈니스 엔티티 및 포트)
├── application/       # 2. 애플리케이션 계층 (유스케이스 서비스 오케스트레이션)
├── infrastructure/    # 3. 인프라 계층 (구체적인 외부 연동 어댑터 및 DI 컨테이너)
└── presentation/      # 4. 프레젠테이션 계층 (웹서버 FastAPI 및 텔레그램 봇 인터페이스)
```

### 계층별 역할 및 설명

#### 1. 도메인 계층 (`src/evenezer/domain/`)
- 외부 라이브러리 및 외부 환경에 의존하지 않는 가장 순수한 비즈니스 로직 영역입니다.
- 핵심 엔티티: `Stock`(주식 종목), `Node`(마인드맵 노드), `Board`(Miro 보드)
- 추상 포트 정의: 외부 스토리지나 API로 나가는 아웃고잉 포트(`ports.py`)가 선언되어 있습니다.
- 하위 비즈니스 도메인: `news`, `statistics`, `financials`, `heatmap`, `analytics`

#### 2. 애플리케이션 계층 (`src/evenezer/application/services/`)
- 도메인 엔티티와 포트를 사용하여 핵심 비즈니스 유스케이스를 오케스트레이션합니다.
- 주요 서비스:
  - `BoardCommandService` / `BoardQueryService`: 보드 데이터의 변경 및 조회 비즈니스 처리
  - `BoardFileSyncService`: 보드의 상태를 Google Drive와 양방향 동기화
  - `StatisticsService`: 순매수, 상한가, 무상증자, 신규 상장 등의 지표 가공 및 업데이트
  - `HeatmapService`: 테마 및 수급 기반의 주식 히트맵 이미지 롤업
  - `NewsService`: 종목 연관 뉴스의 수집 및 분류 관리

#### 3. 인프라 계층 (`src/evenezer/infrastructure/`)
- 도메인 계층의 추상 포트를 구현하는 **어댑터(Adapters)**와 영속성 데이터 저장소의 구체 클래스가 위치합니다.
- 주요 어댑터:
  - `adapters/google/`: Google Drive API 기반 파일 업로드/다운로드
  - `adapters/krx/`: KRX API 로그인 및 세션 관리, 시장 통계 데이터 스크래핑
  - `adapters/miro/`: Miro REST API 클라이언트 구현 및 마인드맵 노드 동적 생성
  - `adapters/scraper/`: httpx + BeautifulSoup 기반 네이버 뉴스 등 웹 크롤링
  - `adapters/disclosure/`: DART API 연동을 통한 공시 및 재무 정보 취득
  - `adapters/financial/`: 엑셀 재무제표 파일 파싱 어댑터
  - `adapters/local/`: 데이터 영속성을 위한 로컬 파일 시스템 리포지토리
- 의존성 주입(DI): `infrastructure/container.py` 파일의 Singleton 컨테이너가 모든 인프라 어댑터와 애플리케이션 서비스를 라이프사이클에 맞게 바인딩하고 의존성을 주입합니다.

#### 4. 프레젠테이션 계층 (`src/evenezer/presentation/`)
- 오케스트레이션에 진입하기 위한 사용자 인터페이스를 담당합니다.
- **Web UI (`presentation/web/`)**: FastAPI 기반의 웹서버입니다. Jinja2 템플릿을 활용해 종목 상태, 통계, 히트맵 리포트를 대시보드로 구성하고, WebSocket(`/ws/logs`)을 통해 백그라운드 수집 로그를 대시보드 화면에 실시간 브로드캐스팅합니다.
- **Telegram Bot (`presentation/telegram/`)**: 대화형 인터페이스를 지원하는 봇 제어부로, 사용자 조작에 따른 보드 동기화나 백그라운드 동작을 트리거합니다.

---

## 📂 디렉토리 구조 (Directory Layout)

```
mindmap/
├── .env.example            # 환경변수 템플릿 파일
├── CLAUDE.md               # 클로드 에이전트 가이드용 축약 문서
├── Dockerfile              # 도커 컨테이너 빌드 파일
├── docker-compose.yml      # 도커 컴포즈 실행 정의
├── justfile                # 윈도우 파워쉘 대응 개발 숏컷 (just CLI 도구용)
├── pyproject.toml          # uv 기반 파이썬 의존성 및 프로젝트 스크립트 메타데이터
├── setup.bat               # Windows 환경 자동 초기화 스크립트
├── run_services.bat        # Windows 환경 원클릭 다중 프로세스 기동 스크립트
├── data/                   # 런타임 수집 데이터 보관소
│   ├── board/              # 백업용 보드 JSON 데이터 (Google Drive와 동기화)
│   ├── news/               # 종목별 스크랩 뉴스 아카이브
│   ├── report/             # 애널리스트 리포트 데이터
│   ├── pdf/                # 저장된 PDF 데이터
│   ├── financial_statements/ # DART API / 로컬 캐싱된 기업 재무제표 JSON
│   └── statistics/         # 순매수, 주식 분할, 신규 상장 등 도메인별 수집된 통계 데이터
├── secrets/                # Google Drive API OAuth 인증 토큰 및 Credential 파일 디렉토리
│   └── client_secret.json  # 구글 클라우드 콘솔에서 발급받은 클라이언트 시크릿 파일
├── src/                    # 어플리케이션 소스 코드
├── tests/                  # 전체 테스트 코드
│   ├── unit/               # 외부 의존성이 제거된 빠른 단위 테스트
│   └── integration/        # 외부 API(샌드박스/모킹) 연동 통합 테스트
└── fixtures/               # 테스트용 모킹 데이터 및 파일들
```

---

## 🛠️ 시작하기 (Getting Started)

### 요구사항 (Prerequisites)
- **Python >= 3.12**
- **uv (Python Package Manager)**: 초고속 파이썬 패키지 매니저로, 프로젝트의 모든 가상환경 관리 및 패키지 설치는 `uv`를 사용합니다.

### 1. 환경 설정 (Configuration)
프로젝트 루트 디렉토리에 `.env` 파일을 만들고 아래의 키값들을 채워 넣어야 합니다.  
*(참고: `.env`에 들어가는 토큰 및 패스워드는 민감한 정보이므로 절대 git에 커밋해서는 안 됩니다)*

```env
# Miro API Access Token
MIRO_ACCESS_TOKEN=your_miro_access_token
MIRO_REFRESH_TOKEN=your_miro_refresh_token

# Google Drive Folder IDs (Miro 데이터 동기화 및 보고서 업로드 위치)
GOOGLE_DRIVE_REPORT_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_SUPPLY_DEMAND_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_CEILLING_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_CAPITAL_INCREASE_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_BONUS_SHARE_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_CONVERTIBLE_BOND_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_BW_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_NEW_LISTING_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_NEWS_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_WEEKLY_CHANGE_ID=your_gdrive_folder_id
GOOGLE_DRIVE_FINANCIAL_STATEMENTS_ID=your_gdrive_folder_id
GOOGLE_DRIVE_THEME_FOLDER_ID=your_gdrive_folder_id
GOOGLE_DRIVE_STOCK_SPLIT_ID=your_gdrive_folder_id
GOOGLE_DRIVE_HEATMAP_FOLDER_ID=your_gdrive_folder_id

# Telegram Bot API Token
TELEGRAM_API_TOKEN=your_telegram_bot_token

# KRX Scraping Credentials (거래소 로그인 정보)
KRX_USERNAME=your_krx_id
KRX_PASSWORD=your_krx_password

# External Report Scraping Credentials (선택사항)
WISE_REPORT_USERNAME=your_wise_report_id
WISE_REPORT_PASSWORD=your_wise_report_password
```

### 2. 구글 인증 정보 설정 (Secrets)
Google Drive API와의 통신을 위하여 Google Cloud Console에서 OAuth 2.0 클라이언트 정보를 생성하고 JSON으로 다운로드받아 다음 경로에 위치시켜야 합니다.
- `secrets/client_secret.json`

---

## 🏃 로컬 개발 및 실행 가이드

### 1. 환경 구성 및 초기 설치
Windows 환경의 경우, 제공된 셋업 배치 파일을 실행하여 가상환경 구축 및 Playwright 스크래퍼용 브라우저 설치를 자동 진행할 수 있습니다.
```bash
# Windows
.\setup.bat

# 기타 OS (직접 명령 수행 시)
uv sync
uv run playwright install
```

### 2. 서비스 기동 방법 (FastAPI 웹 및 텔레그램 봇)

#### 배치 파일 실행 (Windows 원클릭 실행)
```bash
.\run_services.bat
```
- 배치 파일 실행 시, 자동으로 FastAPI 웹 서버(포트 8090)와 텔레그램 봇이 각자 새로운 콘솔 창에서 백그라운드로 기동합니다.

#### 개별 실행 (직접 명령어 실행)
```bash
# FastAPI 웹 서버 기동 (8090 포트 기본 실행)
uv run evenezer

# 텔레그램 봇 기동
uv run evenezer-bot
```

### 3. Docker 환경 기동
Docker 및 `just` 커맨드가 설치되어 있는 경우 다음과 같이 단축 명령어로 시스템을 제어할 수 있습니다.
```bash
# 백그라운드로 도커 컨테이너 빌드 및 실행
just docker-up

# 컨테이너 실시간 로그 확인
just docker-logs

# 컨테이너 중지 및 관련 리소스 정리
just docker-down

# 수집 데이터 및 로컬 캐시를 제외한 클린 압축본 생성
just zip
```

---

## 🧪 테스트 실행 가이드

테스트 코드는 `pytest`를 기본 테스트 프레임워크로 사용합니다.

```bash
# 전체 테스트 실행
uv run pytest

# 단위 테스트만 실행 (외부 의존성 없음, Mocking 동작)
uv run pytest -m unit

# 통합 테스트만 실행 (DB, API, 파일 등 외부 연동 테스트)
uv run pytest -m integration

# 테스트 커버리지 리포트 확인
uv run pytest --cov=src
```

> **경고**: 외부 API(KRX, Google Drive, Miro, Telegram 등)가 포함된 테스트를 작성하거나 실행할 때는 절대 운영 환경에 영향을 미쳐서는 안 되며, Mock 패키지를 이용하거나 격리된 별도 샌드박스 테넌트 토큰을 사용하여 실행해야 합니다.

---

## 🛠️ 개발 방법론 및 DoD (Definition of Done)

본 프로젝트는 안전하고 체계적인 코드 유지보수를 위하여 아래의 워크플로우와 완료 기준을 강력하게 준수해야 합니다.

### 1. 브랜치 전략 (Branch Strategy)
모든 작업은 다음 접두사 규칙에 따라 master 브랜치로부터 파생된 임시 브랜치를 만들고 작업 후 Pull Request(병합 요청)를 보냅니다.

- **`master` 브랜치에 직접 커밋 및 푸시는 원칙적으로 금지**합니다.
- 병합 시에는 Fast-forward를 지양하고, 병합의 흐름을 한눈에 볼 수 있도록 `--no-ff` 옵션을 명시하여 병합 커밋 로그를 생성합니다.
- 병합 커밋 메시지에는 작업 리포트(변경 내용, 주요 설계 결정, 테스트 검증 결과)를 상세히 기재합니다.

| 접두사 | 용도 |
|:---|:---|
| `feature/` | 새로운 기능 개발 및 데이터 크롤러 추가 등 |
| `fix/` | 버그 수정 |
| `refactor/` | 로직 성능 최적화, 파일 위치 변경 등 구조 개선 |
| `chore/` | 의존성 패키지 추가, 설정 변경, CI/CD 변경 등 |
| `hotfix/` | 운영 환경에서 발견된 크리티컬한 버그 긴급 수정 |

### 2. 커밋 메시지 컨벤션
깃 커밋은 항상 테스트가 정상 통과된 상태(Green)에서 수행하며, 아래 포맷을 유지합니다.

```
<Emoji> <Type>: <Subject>

- 작업 상세 내용 첫 번째
- 작업 상세 내용 두 번째
```

- **Emojis & Types**:
  - ✨ `feat`: 새로운 기능 추가
  - 🐛 `fix`: 버그 수정
  - ♻️ `refactor`: 리팩토링
  - ✅ `test`: 테스트 추가 및 검증 완료
  - 📝 `docs`: 문서 작성 및 업데이트
  - 🚀 `chore`: 빌드, 패키지, 설정 변경
- **주제(Subject) 및 본문**: 반드시 한글로 핵심 요점을 작성합니다.

*예시:*
```
✨ feat: Miro 보드 노드 신규 레이아웃 자동 정렬 규칙 추가

- 연결관계 분석 후 상위 노드 아래에 하위 노드가 정렬되도록 알고리즘 개선
- 겹침 감지 및 보정 로직 추가
```

### 3. 완료 기준 (Definition of Done - DoD)
브랜치를 `master`에 병합하기 전, 아래 체크리스트를 실행하고 검증을 통과해야 합니다.

- [ ] 관련 단위 테스트(`unit`) 작성 완료 및 통과
- [ ] 통합 테스트(`integration`) 통과 및 기존 시스템 회귀 오류가 없음 확인
- [ ] **정적 분석 파이프라인** 통과
  - `uv run ruff check src/` : 린트 오류 없음
  - `uv run ruff format --check src/` : 스타일 포맷팅 일치
  - `uv run ty check src/` : 타입 어노테이션 오류 없음
  - `uv run radon cc -n C src/` : 코드 순환 복잡도가 **C 등급 미만**(즉, A 또는 B 등급의 복잡도 10 이하만 허용)
- [ ] 변경 사항에 대한 병합 로그 작성 준비 완료
