# uv 및 Docker 배포

VulRIS는 네트워크 서비스가 아니라 소스 저장소를 읽어 로컬 SQLite 인덱스를 만드는 CLI다. 분석할 저장소는 읽기 전용으로 연결하고, 생성되는 데이터 디렉터리만 쓰기 가능하게 둔다.

## uv

Python 3.11 또는 3.12와 [uv](https://docs.astral.sh/uv/)가 필요하다.

한 번 실행하거나 독립 CLI로 설치할 수 있다.

```bash
uvx --from git+https://github.com/VulRIS-data/VulRIS.git vulris --version
uv tool install git+https://github.com/VulRIS-data/VulRIS.git
vulris --version
```

잠금 파일과 정확히 같은 환경을 재현할 때는 저장소를 복제한다.

```bash
git clone https://github.com/VulRIS-data/VulRIS.git
cd VulRIS
uv sync --locked
uv run --no-sync vulris --version
uv run --no-sync vulris --data-dir ./index --project ./tests/fixture build
uv run --no-sync vulris --data-dir ./index --project ./tests/fixture overview
```

`uv.lock`은 애플리케이션 실행에 필요한 Python 의존성을 고정한다. 의존성을 바꾸려면 `pyproject.toml`을 수정하고 `uv lock`과 전체 시험을 다시 실행한다.

## Docker

이미지를 로컬에서 만든다.

```bash
docker build -t vulris:local .
docker volume create vulris-data
docker run --rm \
  --mount type=bind,src="$PWD/tests/fixture",dst=/source,readonly \
  --mount type=volume,src=vulris-data,dst=/data \
  vulris:local --data-dir /data --project /source build
docker run --rm \
  --mount type=bind,src="$PWD/tests/fixture",dst=/source,readonly \
  --mount type=volume,src=vulris-data,dst=/data \
  vulris:local --data-dir /data --project /source overview
```

PowerShell에서는 bind source에 절대 경로를 사용한다.

```powershell
$project = (Resolve-Path .\tests\fixture).Path
docker run --rm `
  --mount "type=bind,src=$project,dst=/source,readonly" `
  --mount "type=volume,src=vulris-data,dst=/data" `
  vulris:local --data-dir /data --project /source build
```

컨테이너는 UID/GID `10001:10001`로 실행된다. Linux에서 호스트 디렉터리를 `/data`에 직접 bind mount하려면 그 사용자가 쓸 수 있도록 권한을 부여하거나 Compose의 기본 named volume을 사용한다.

## Docker Compose

기본 예제 저장소 대신 실제 프로젝트를 지정한다.

```bash
VULRIS_PROJECT=/absolute/path/to/project docker compose run --rm vulris build
VULRIS_PROJECT=/absolute/path/to/project docker compose run --rm vulris overview
```

PowerShell에서는 다음과 같이 지정한다.

```powershell
$env:VULRIS_PROJECT = (Resolve-Path C:\path\to\project).Path
docker compose run --rm vulris build
docker compose run --rm vulris overview
```

`vulris-data` named volume은 명령 사이에 인덱스를 보존한다. 삭제하려면 `docker compose down -v`를 실행한다.

## 운영 원칙

- 분석할 소스는 `/source`에 읽기 전용으로 연결한다.
- `/data`에는 SQLite DB, content-addressed blob과 parsing cache가 저장된다.
- 컨테이너는 소스 파일을 실행하지 않지만, 신뢰하지 않는 저장소를 분석할 때에도 네트워크와 추가 권한을 부여하지 않는다.
- 동일 입력과 분석 버전의 스냅샷은 재사용하며, 실험에 사용한 동결 DB는 별도 보존한다.
