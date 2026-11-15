# VulRIS 정적 관계 정보 구성기

VulRIS 정적 관계 정보 구성기는 여러 언어로 작성된 소스 저장소를 읽어 선언, 호출 지점, import, 포함, 상속 후보와 웹 프레임워크 단서를 SQLite 스냅샷으로 만드는 로컬 전처리 도구다. LLM이나 외부 API를 호출하지 않으며 취약점을 자동 판정하지 않는다. 생성 결과는 분석자가 원본 코드의 관련 위치와 연결 후보를 빠르게 조회하기 위한 자료다.

## 지원 범위

| 언어 | 선언 | import 연결 | 상속 후보 | 프레임워크 단서 |
| --- | --- | --- | --- | --- |
| Java | 클래스, 메서드, 생성자, 필드 | 패키지와 import 문맥(간선 없음) | extends, implements, override | Spring |
| Python | 모듈, 클래스, 함수, 메서드, 생성자 | import, from import, 상대 import | 클래스 기반 클래스 | FastAPI, Django, Flask |
| JavaScript | 모듈, 클래스, 함수, 메서드 | ES module, `require` 상대경로 | extends | Express, NestJS |
| TypeScript | JavaScript 범위와 interface, enum, namespace | ES module 상대경로, `.ts`/`.tsx` | extends, implements | Express, NestJS |
| Go | struct, interface, 함수, 수신자 메서드 | import 경로와 디렉터리 패키지 | struct embedding | Gin, net/http |
| C# | namespace, class, interface, struct, enum, method | using 네임스페이스 | 상속과 구현 | ASP.NET Core |
| C | struct, enum, 함수 정의 | `#include "..."` | 없음 | 민감 API 이름 단서 |
| C++ | namespace, class, struct, enum, 함수, `Type::method` 정의 | `#include "..."` | 기반 클래스 | 민감 API 이름 단서 |
| Rust | mod, struct, enum, trait, impl 메서드, 함수 | `use crate::`, `self::`, `super::`, `mod x;` | `impl Trait for Type` | Axum, Actix Web |
| PHP | namespace, class, interface, trait, enum, 함수, 메서드 | `use`, include/require | extends, implements | Laravel, 슈퍼글로벌 |
| Ruby | module, class, method | `require_relative`, `require` | 상위 클래스 | Rails |
| Kotlin | class, interface, object, 함수, 보조 생성자 | import | 상위 클래스와 interface | Spring 어노테이션 |
| Swift | class, struct, enum, protocol, extension 메서드, 함수, init | 같은 모듈 전체 | 상위 클래스와 protocol | 민감 API 이름 단서 |

모든 연결은 구문 기반 후보다. 대상이 하나면 `candidate`, 둘 이상이면 `ambiguous`, 없으면 `unresolved`로 저장한다. `resolved`는 향후 의미 분석 백엔드를 위해 예약했으며 현재 생성하지 않는다. 동적 디스패치, reflection, 런타임 의존성 주입, Go의 암묵적 interface 충족, 데이터 흐름과 제어 흐름은 증명하지 않는다.

### 호출 후보를 좁히는 순서

Java는 기존 연구 구현의 연결 규칙(이름, 인자 수, 필드/매개변수/지역 변수 타입)을 그대로 쓴다. 나머지 언어는 다음 순서로 후보를 좁히고, 쓴 방법을 호출 행의 `strategy`에 남긴다.

1. 생성자 구문(`new X()`, `X()`, `X.new`, `X::new()`)은 해당 타입의 생성자 또는 타입
2. `self`, `this`, Go 수신자 변수, `super`는 감싸는 타입과 그 상위 타입의 메서드
3. 매개변수 타입, 지역 변수 선언, 생성 식, 필드 선언으로 타입을 알 수 있는 수신 객체
4. 타입 이름이나 import한 모듈 별칭을 수신 객체로 쓴 호출
5. 수신 객체가 없는 호출은 같은 클래스(암묵적 수신자 언어), 같은 파일, import한 이름, 같은 디렉터리 순
6. 위가 모두 해당하지 않을 때만 같은 언어 계열에서 이름과 인자 수로 찾는다(`name_arity`)

수신 객체가 외부 패키지 별칭이거나 프로젝트 밖 타입이면 프로젝트 안의 같은 이름 함수와 연결하지 않고 `unresolved`로 둔다(`external_receiver`, `external_type`). 반환 타입은 추론하지 않으므로 `a.b().c()` 같은 연쇄 호출의 뒤쪽은 대개 `name_arity` 또는 `unresolved`다.

### 언어별 제한

| 언어 | 알려진 제한 |
| --- | --- |
| Python | 동적 속성, 데코레이터가 바꾼 함수, monkey patching은 따라가지 않는다. 변수와 상수는 기호로 저장하지 않는다. |
| JavaScript, TypeScript | 타입 검사기를 쓰지 않는다. TS 타입은 선언된 주석만 읽는다. `tsconfig` paths, package exports, `module.exports` 재구성은 해석하지 않는다. |
| Go | `go.mod` 모듈 경로 대신 import 경로의 끝과 디렉터리를 맞춘다. interface 충족은 계산하지 않는다. |
| C, C++ | 전처리기, 매크로, `compile_commands.json`을 쓰지 않는다. 함수 선언(prototype)은 기호로 저장하지 않고 정의만 저장한다. 오버로드와 템플릿은 인자 수로만 구분한다. |
| C# | partial class, 확장 메서드, LINQ 식은 연결하지 않는다. |
| Rust | 매크로를 펼치지 않는다. trait 메서드는 이름으로 연결하고 제네릭 경계는 해석하지 않는다. |
| PHP | 가변 함수, `__call`, Laravel facade의 실제 대상은 해석하지 않는다. |
| Ruby | 괄호와 인자가 모두 없는 메서드 호출은 지역 변수와 구별할 수 없어 호출로 저장하지 않는다. mixin(`include`)과 `method_missing`은 연결하지 않는다. |
| Kotlin | tree-sitter-kotlin 1.1은 한 줄에 몰아 쓴 일부 선언에서 구문 오류를 낸다. 오류는 `parse_errors`에 기록된다. 확장 함수와 주 생성자는 별도 기호로 만들지 않는다. |
| Swift | 다른 Swift 모듈 import는 외부로 둔다. 인자 레이블로 구분되는 오버로드는 인자 수로만 구분한다. |

## 설치

### uv 권장 경로

Python 3.11 또는 3.12와 [uv](https://docs.astral.sh/uv/)를 준비한다. 저장소의 `uv.lock`을 사용하면 시험한 의존성 조합을 그대로 설치한다.

설치 없이 GitHub 최신판을 바로 실행할 수 있다.

```powershell
uvx --from git+https://github.com/VulRIS-data/VulRIS.git vulris --version
```

반복해서 사용할 때는 독립 도구로 설치한다.

```powershell
uv tool install git+https://github.com/VulRIS-data/VulRIS.git
vulris --version
```

개발하거나 잠금 파일과 정확히 같은 환경을 재현하려면 저장소를 복제한다.

```powershell
git clone https://github.com/VulRIS-data/VulRIS.git
cd VulRIS
uv sync --locked
uv run --no-sync vulris --version
```

### pip 대체 경로

Python 3.11 이상에서 별도 가상환경을 권장한다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

tree-sitter 0.25 계열과 각 언어 문법 패키지 버전은 `requirements.txt`에 고정된 범위로 설치된다. 특정 문법 패키지가 없거나 로드되지 않으면 해당 언어만 `unavailable`로 기록하고 나머지 언어의 빌드는 계속한다.

## Docker

분석할 소스는 읽기 전용으로, 인덱스는 named volume에 연결한다.

```powershell
docker build -t vulris:local .
$env:VULRIS_PROJECT = (Resolve-Path .\tests\fixture).Path
docker compose run --rm vulris build
docker compose run --rm vulris overview
```

컨테이너는 비특권 사용자로 실행되고 소스 저장소를 실행하지 않는다. Linux, PowerShell, bind mount와 데이터 권한에 관한 전체 예시는 [uv 및 Docker 배포 문서](docs/deployment.ko.md)에 있다.

## 빠른 시작

보관된 연구 DB를 쓰기 대상으로 지정하지 말고 새 데이터 폴더를 사용한다.

```powershell
uv run --no-sync vulris --data-dir "E:\work\relation-data" --project "E:\work\sample-project" build
uv run --no-sync vulris --data-dir "E:\work\relation-data" --project "E:\work\sample-project" overview
uv run --no-sync vulris --data-dir "E:\work\relation-data" --project "E:\work\sample-project" files --language python
uv run --no-sync vulris --data-dir "E:\work\relation-data" --project "E:\work\sample-project" symbols Service --language typescript
uv run --no-sync vulris --data-dir "E:\work\relation-data" --project "E:\work\sample-project" facts
```

빌드 결과의 `snapshot_id`로 특정 불변 버전을 조회할 수 있다. 읽기 명령은 다음과 같다.

| 명령 | 용도 |
| --- | --- |
| `overview` | metrics와 capabilities 확인 |
| `files [text]` | 파일 목록, `--language` 필터 지원 |
| `symbols [text]` | 선언 검색, `--kind`, `--language` 필터 지원 |
| `symbol <id>` | 선언 세부 정보 |
| `relations <id>` | 들어오고 나가는 관계 후보 |
| `facts [--kind kind]` | 라우트, 입력, 권한, 설정, 민감 호출 단서 |
| `search <text>` | 원본 소스 전문 검색 |
| `read <path>` | 원본 소스 줄 범위 읽기 |
| `context <id>` | 선언, 관계, 호출, 단서와 소스 묶음 조회 |

## 처리 구조

```text
source repository
  -> snapshot-v9 collector
  -> language registry and tree-sitter frontends
  -> framework evidence rules
  -> language-family candidate resolver
  -> schema-v2 SQLite snapshot
  -> read-only query interface
```

`languages/`는 언어마다 하나의 frontend 모듈을 둔다. 공통 추출기(`treesitter.py`)가 순회와 기호 생성을 맡고, 각 언어 모듈은 이름, 매개변수, 호출식, import, 상위 타입, 타입 선언을 읽는 작은 hook만 구현한다. `frameworks/`는 Spring, FastAPI, Django, Flask, Express, NestJS, ASP.NET, Gin, Rails, Laravel, Axum, Actix 단서를 언어 파싱과 분리한다. `resolver/`는 JavaScript와 TypeScript, C와 C++처럼 호환되는 계열 안에서만 후보를 연결한다. 언어별 파서 버전, 규칙 버전, 프레임워크 규칙 버전과 resolver 버전은 스냅샷 서명과 파싱 캐시 키에 포함된다.

Java 공개 행의 ID와 `data` JSON은 기존 연구 구현과 동일하게 유지한다. 새 `language`와 `provenance` 값은 스키마 v2의 별도 열에 저장한다. Spring 단서 ID에 필요한 구문 시작 바이트는 `data` 밖의 `anchors` 맵으로 전달한다. `tests/golden`의 두 기준 파일이 Java 동일성을 검증한다.

## 저장 결과

`--data-dir` 아래에 다음 항목이 생긴다.

```text
relations.sqlite3
blobs/<sha256>
parse_cache/<cache-key>.json
```

원본 파일은 SHA-256 이름의 blob으로 저장하고 SQLite는 해당 해시를 참조한다. `snapshot_id`는 프로젝트 ID, 수집 내용 해시와 분석 서명으로 결정된다. 같은 프로젝트의 같은 입력과 같은 분석 버전은 같은 스냅샷을 재사용한다. 자세한 테이블과 JSON 필드는 [데이터구조.md](데이터구조.md)에 있다.

## 시험

```powershell
uv run --no-sync python -m unittest discover -s tests -v
```

시험에는 다음 항목이 포함된다.

- Java 최소 fixture와 Spring fixture의 byte-equivalent golden 회귀
- 12개 언어 각각의 2~3개 파일 fixture에서 기대한 교차 파일 `CALLS` 후보, 상속/구현 간선, route 경로와 input/guard 단서
- Java, Python, TypeScript, Go, Rust 혼합 저장소를 서로 다른 데이터 폴더에 두 번 빌드했을 때 스냅샷 ID와 모든 행이 같은지
- parse cache 재사용(Java 포함)과 재사용 시 결과 동일성
- 외부 패키지 수신 객체가 프로젝트의 같은 이름 함수와 연결되지 않는지
- 모든 지원 언어의 files, symbols, relations, read, context 조회
- 문법 패키지 누락 시 다른 언어 계속 처리와 capabilities 표시
- 구문 오류 metrics와 `.h` 파일의 C/C++ 결정
- 스키마 v1에서 v2로의 이전과 기존 행 보정

fixture 시험은 각 언어의 대표 구문만 다룬다. 실제 저장소에서는 다음을 따로 확인했다. CWE-Bench-Java case-004(Java 727개 파일)에서 이전 구현과 symbols, calls, edges, facts 행이 모두 같았고, pip 패키지 소스(Python 488개 파일)에서 추출 실패와 구문 오류 없이 빌드됐다. 다른 언어의 대규모 저장소 정확도는 측정하지 않았다.

## 안전과 해석

- `.gitignore`와 `.relationignore`를 적용하며 일반적인 비밀 파일명, 심볼릭 링크, 바이너리를 수집하지 않는다.
- 파일당 5 MB, 전체 700 MB, 25,000개 파일 상한을 둔다.
- 프레임워크 단서와 `security_call`은 이름과 구문 위치를 찾는 탐색 단서다. 실제 인증 적용, 실행 가능성 또는 취약점을 의미하지 않는다.
- 설정 파일의 존재는 해당 설정이 활성화됐다는 뜻이 아니다.
- 연구에 사용한 동결 DB와 현재 구현으로 새로 만든 스냅샷은 구분해야 한다.

## 프로젝트 구성

- `relation_index.py`: 설치 없이 저장소에서 `vulris` CLI를 실행하는 진입점
- `src/relation_index/cli.py`: 빌드와 조회 CLI
- `src/relation_index/languages/`: 언어 프런트엔드와 registry
- `src/relation_index/frameworks/`: 프레임워크와 민감 호출 단서
- `src/relation_index/resolver/`: import, 호출, 상속 후보 연결
- `src/relation_index/snapshot.py`: 안전한 파일 수집과 blob 보관
- `src/relation_index/storage.py`: SQLite 스키마, 이전, 작업 상태
- `src/relation_index/queries.py`: 읽기 전용 조회
- `tests/fixtures/`: 지원 언어별 재현 입력
- `tests/golden/`: Java 호환성 기준 결과

보관된 Vul4J+ 실험 입력은 이 폴더의 새 빌드 결과와 별개다. 논문 재현에는 실험 당시 보관한 스냅샷 ID와 해시를 사용한다. 구현 출처와 호환성 정책은 [구현출처.md](구현출처.md)에 기록한다.
