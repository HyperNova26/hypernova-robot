# AI/CV 로드맵 페이지

HyperNova AI/CV 팀의 스프린트별 진행 현황을 보여 주는 GitHub Pages 브랜치입니다.
코드 브랜치(`main`)와 기록을 섞지 않으려고 이 페이지만 담은 별도 브랜치(`gh-pages`)로 둡니다.

- 주소: <https://hypernova26.github.io/hypernova-robot/>
- 페이지를 열면 오늘 날짜의 상태 박스가 화면 맨 위에 옵니다. 위로 스크롤하면 지난 작업, 아래로 내리면 진행 중이거나 예정된 작업이 보입니다.
- 가운데 줄기가 시간축입니다. 보행 가지는 왼쪽, 인지 가지는 오른쪽에 있고, 공통 카드는 줄기 위에 놓입니다.
- 카드를 누르면 해당 Notion 업무가 열립니다.

## 파일

| 경로 | 역할 |
| --- | --- |
| `index.html` | 화면 전체 (HTML, CSS, JS 한 파일) |
| `data/roadmap.json` | 팀원, 마일스톤, 가지 데이터. 평소에는 이 파일만 고칩니다 |
| `.nojekyll` | GitHub Pages가 Jekyll 처리를 건너뛰게 합니다 |

## 가지 추가하기

1. [전체 업무 DB](https://app.notion.com/p/3b445bd87178802796e1dbf0e35e6de5?v=3b445bd87178802c8bda000c79be7d24)에 업무를 만듭니다.
   - `팀`: AICV
   - `담당자`: 공통은 허재원, 보행은 정찬원·조재대, 인지는 김완준·장승민
   - `구분`: 작업, `상태`: 예정, `마감일`: 해당 스프린트 안의 날짜
   - 본문 맨 위에 `AICV 로드맵 G-번호`와 이 페이지 링크를 담은 콜아웃을 둡니다.
2. `data/roadmap.json`의 `branches`에 항목을 추가하고 커밋합니다. G-번호는 이어서 붙입니다.

```json
{
  "id": "G-002", "area": "walk", "milestone": "S1",
  "title": "업무 제목", "status": "예정", "due": "2026-11-08",
  "url": "https://app.notion.com/p/..."
}
```

## 데이터 형식

`branches` 항목:

| 필드 | 값 |
| --- | --- |
| `id` | `G-001` 형식. 비워 두면 번호 없이 표시 |
| `area` | `common`(공통), `walk`(보행), `perc`(인지) |
| `milestone` | `milestones`의 `id` |
| `status` | Notion `상태`와 같은 값: `Backlog`, `예정`, `진행`, `검토`, `블로킹`, `완료` |
| `due` | `YYYY-MM-DD`. 완료 전에 이 날짜가 지나면 "마감 지남"으로 표시 |
| `url` | Notion 업무 주소. 비워 두면 전체 업무 DB로 연결 |

`milestones` 항목은 `id`, `name`, `start`, `end`를 가집니다. `name`은 비워 둬도 됩니다.
`"gap": true`는 작업이 없는 기간(시험 기간)으로 줄기를 점선으로 그립니다. `"showId": false`는 알약에 ID를 숨깁니다.

상태 박스의 "지금 마일스톤"은 아직 끝나지 않은 첫 마일스톤입니다. 그 앞의 마일스톤은 상태 박스 위로 올라갑니다.

## 확인하기

```sh
python3 -m http.server 8000
```

<http://localhost:8000>에서 열고, 주소 끝에 `?today=2026-11-20`을 붙이면 다른 날짜 기준으로 볼 수 있습니다.
`index.html`을 파일로 바로 열면 브라우저가 JSON 읽기를 막으니 위처럼 로컬 서버로 엽니다.

## 라이선스

`main` 브랜치의 [`LICENSE.md`](https://github.com/HyperNova26/hypernova-robot/blob/main/LICENSE.md)를 따릅니다. 코드는 Apache-2.0, 문서는 CC BY 4.0입니다.
