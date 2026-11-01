# 자료 편집과 마크다운 생성

[읽기 목록](README.md) · [저장소 처음으로](../README.md)

## 수정할 곳

- `data/NN-*.json`: 원문·현토·번역·기존 편집 구분·주석·용어의 편집 원본이다.
- [project.json](../data/project.json): 수록 파일과 순서, 원문 검증 방식을 기록한다.
- [source-lock.json](../data/source-lock.json): 고정 CBETA URL과 전체 XML 파일의 SHA-256을 기록한다. 원래 XML과 헤더는 로컬 캐시에 온전히 보존한다.
- [import-manifest.json](../data/import-manifest.json): 반입 커밋과 보관 파일의 체크섬이다.
- [STYLE.md](../STYLE.md)와 [SOURCES.md](../SOURCES.md): 현재 번역 원칙과 검토 근거를 관리한다.

`reader/` 경전 문서는 Python으로 생성한다. 직접 고치지 않는다. 원문·번역·현토·주석은 LLM으로 다시 전사하지 않고 기존 문서에서 코드로 옮겼다. 원문의 문법·시대·전승을 새로 해석하거나 본문에 교리 해설을 추가하지 않았다.

## 구성과 확인 범위

주된 읽기판은 제목에서 한글 번역으로 바로 이어지고 주석과 한문·현토를 같은 문서 아래에 둔다. 메뉴와 원전 안내는 아래로 모은다. 대조·주석·용어 문서는 참고 자료다. 기존 장 구분·문단·편집상 소제목·주 표식을 보존한다.

금강경은 기존 한글 문단과 한문·현토 단위가 일대일이 아니다. 32분의 독서 구분을 유지하고 분 전체를 대조하며 새 구절별 정렬이나 주석 대응을 확정하지 않았다. 용어 대응은 기존 SOURCES의 주요 용어 표를 그대로 옮긴 기록이다.

관리 ID는 고정 연결 지점으로 쓰며 보이는 본문 제목에 끼워 넣지 않는다. 기존 자료에 없는 산스크리트·팔리 대응을 채우지 않는다. 용어 기록의 반입은 일반 한국어 번역본의 용례 조사를 새로 완료했다는 뜻이 아니다.

`legacy_sections`는 원래 공백과 배치 등 이관 복원을 위한 틀이다. 실제 문구는 각 원문·번역·주석·용어 항목을 참조한다. 보관본은 동결하며 현재 생성과 검증은 편집 자료 및 읽기판을 대상으로 한다.

## 생성과 검증

Python 표준 라이브러리만 사용한다. 다음은 저장소 최상위에서 실행한다. 사이트나 HTML 화면은 만들지 않는다.

```powershell
uv run python scripts/reader.py
uv run python scripts/reader.py --check
uv run python scripts/verify_translation.py --cbeta
uv run python scripts/test_reader.py
```

처음에는 고정 원문을 내려받고 이후 `.cache/sources/`를 사용한다. 매번 전체 파일 체크섬을 확인하며 `--fetch-source`로 다시 받을 수 있다. 기존 원문 검사 규칙은 `scripts/source_checks.py`에 유지했다.

```powershell
uv run python scripts/reader.py --check-migration
```

이것은 최초 반입 커밋의 문서를 정확히 복원하는 이관 검사다. 향후 의도적으로 번역을 수정한 뒤에도 항상 옛 문구와 같아야 한다는 뜻은 아니다. 원문 일치·구조·링크 검사는 번역 의미의 감수를 대신하지 않는다.

최초 반입 재현 도구는 `scripts/import_reader.py --title <제목> --commit <원래 커밋>`이다. 이 저장소의 원래 커밋은 `53943f175fab357c706394d0ea613fb6ebe12ff5`이다. 원고 파일은 현재 보관본이 아니라 지정 커밋에서 읽으며, data 또는 보관본이 이미 있으면 덮어쓰기를 거부한다. 새 격리 환경에서 최초 반입을 재현할 때만 사용한다.
