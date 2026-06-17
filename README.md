# Evenezer (이븐에저)

**Evenezer**는 뉴스 데이터와 주식 데이터를 연동하여 한국 주식 시장의 흐름을 마인드맵(Miro)으로 시각화하고 관리하는 통합 마인드맵 오케스트레이터입니다.

---

## 🛠️ 개발 방법론 (Development Methodology)

본 프로젝트는 안전하고 정교한 코드 변경 및 점진적 기능 확장을 위해 아래의 브랜치 전략과 개발 워크플로우를 강력히 준수합니다.

### 1. 브랜치 전략 (Branch Strategy)

#### 접두사 규칙

| 접두사 | 용도 |
|--------|------|
| `feature/` | 새로운 기능 개발 |
| `fix/` | 버그 수정 |
| `refactor/` | 기능 변화 없는 코드 구조/성능 개선 |
| `chore/` | 빌드, 패키지, 설정 변경 |
| `hotfix/` | 운영 중 치명적 버그 긴급 수정 |

#### 핵심 규칙

1. **`master` 직접 커밋 금지** — 사소한 오타 수정 외 모든 작업은 브랜치를 생성하여 진행한다.
2. **작업 중 원격 push 유지** — 로컬에만 두지 않는다.
3. **병합 시 `--no-ff` 강제** — Fast-forward를 방지하여 명시적인 병합 커밋을 남긴다.
4. **병합 커밋 메시지는 작업 리포트로** — 변경 내용 요약, 설계 결정, 검증 결과를 포함한다.

```bash
git checkout master
git merge --no-ff feature/my-feature
# 커밋 메시지 예시:
# Merge branch 'feature/my-feature'
#
# - 변경 내용: Pre-Trade Guard 로직 추가
# - 설계 결정: fail-closed 방식 채택
# - 검증: unit 5개, integration 2개 통과
```

---

### 2. 커밋 메시지 컨벤션 (Commit Message Convention)

```
<type>: <subject>

[optional body]
```

| type | 용도 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 리팩토링 |
| `test` | 테스트 추가/수정 |
| `chore` | 설정, 패키지 등 |
| `docs` | 문서 |
| `style` | 코드 포맷팅 등 (기능 변경 없음) |

**예시**

```
feat: Pre-Trade Guard 스냅샷 실패 시 fail-closed 처리 추가

- 스냅샷 취득 실패 시 주문 차단
- 예외 로깅 포함
```

> **Green 커밋 원칙**: 커밋은 오직 Green(테스트 통과) 상태에서만 수행합니다. Red(테스트 실패) 상태에서의 커밋은 금지됩니다.

---

### 3. 테스트 구조 및 완료 기준 (Test Structure & Definition of Done)

```
tests/
├── unit/          # 단일 함수/클래스, 외부 의존성 없음 (mock 사용)
└── integration/   # 여러 모듈 연결, 외부 API는 mock 또는 sandbox
```

- **외부 API 차단**: 외부 API(KRX, Google Drive 등) 호출이 포함된 테스트는 반드시 mock 또는 별도 sandbox 환경에서 실행합니다.

#### 완료 기준 (Definition of Done - DoD)

브랜치를 `master`에 병합하기 전 아래 항목을 모두 충족해야 합니다.
- [ ] 관련 단위 테스트 작성 및 통과
- [ ] 통합 테스트 통과 (기존 테스트 회귀 없음)
- [ ] Ruff 린트/포맷 통과 (`uv run ruff check src/`)
- [ ] 타입 검사 통과 (`uv run ty check src`)
- [ ] 병합 커밋 메시지 작성 완료

---

### 4. 작업 워크플로우 (Workflows)

#### A. 신규 기능 (`feature/`)
```
1. 브랜치 생성 → 통합 테스트 + 스텁 작성 (Top-Down)
2. 각 모듈별 Red → Green → Refactor → Lint 반복 (Bottom-Up)
3. 스텁을 실제 코드로 교체 → 통합 테스트 통과 확인
4. DoD 체크 → --no-ff 병합
```

#### B. 버그 수정 (`fix/`)
```
1. 브랜치 생성 → 버그를 재현하는 실패 테스트 작성 (Red)
2. 최소 코드 수정으로 테스트 통과 (Green)
3. 리팩토링 + 전체 회귀 테스트 확인
4. DoD 체크 → --no-ff 병합
```

#### C. 리팩토링 (`refactor/`)
```
1. 브랜치 생성
2. 코드 변경 (기능 변화 없음)
3. 전체 기존 테스트 통과 확인 (회귀 없음이 완료 기준)
4. DoD 체크 → --no-ff 병합
```

#### D. 긴급 수정 (`hotfix/`)
```
1. master에서 즉시 브랜치 생성 (hotfix/issue-name)
2. 최소 범위로 수정 — 범위를 절대 넓히지 않는다
3. 핵심 재현 테스트 1개 이상 작성 및 통과 확인
4. 전체 테스트 생략 가능하나, 수정 범위 인접 테스트는 반드시 실행
5. --no-ff 병합 → 병합 커밋에 원인/수정 내용/재발 방지 기록
```


