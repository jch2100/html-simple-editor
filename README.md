# html-simple-editor

브라우저에서 HTML 파일의 글자를 바로 고치고 **Ctrl+S로 원본 파일에 저장**하는 윈도우용 작은 도구입니다.
AI로 만든 HTML 교안·프로필·보고서에서 문구 몇 개, 줄바꿈 몇 개를 고치려고 코드를 열 필요가 없게 만들었습니다.

A tiny Windows tool to edit the text of a local HTML file in the browser and save it back with Ctrl+S.

## 할 수 있는 것

- 화면에서 글자를 클릭해서 바로 수정
- **Enter = 줄바꿈** (`<br>`), 문단이 쪼개지지 않음
- **Ctrl+S = 원본 파일에 저장**, 직전 버전은 `파일명.html.bak`으로 자동 보관
- 외부 CSS·이미지(상대경로)가 그대로 보임
- 붙여넣기는 서식 없이 글자만
- 최근 파일 5개

**하지 않는 것:** 디자인·배치 변경, 요소 추가·이동. 글자와 줄바꿈 전용입니다.

## 설치 (일반 사용자)

1. [Releases](https://github.com/jch2100/html-simple-editor/releases)에서 `HTML편집.zip`을 받아 압축을 풉니다.
2. `HTML편집.exe`를 더블클릭합니다.
   서명되지 않은 프로그램이라 처음 한 번 **"Windows의 PC 보호"** 창이 뜹니다. **[추가 정보] → [실행]** 을 누르세요.

## 사용법

1. 실행하면 브라우저에 시작 화면이 열립니다. **[열기]** 로 HTML 파일을 고릅니다.
2. 글자를 클릭해서 고치고, Enter로 줄을 바꾸고, **Ctrl+S**로 저장합니다.
3. 화면 오른쪽 아래 막대에서 **[다른 파일 열기]**, **[끄기]**.

파일 경로를 인자로 주면 시작 화면을 건너뛰고 바로 편집합니다. 바로가기의 "보내기" 메뉴에 넣어 두면 편합니다.

## 주의

- Windows + Chrome/Edge 전용입니다.
- **자바스크립트가 내용을 그리는 HTML은 저장하지 마세요.** 화면에 그려진 결과가 그대로 파일에 굳습니다.
- 빌드 도구가 만들어 내는 파일(`dist/` 등)을 고치면 다음 빌드 때 덮어써집니다. 같은 폴더에 사본(`_final.html`)을 만들어 고치는 것을 권합니다.

## 동작 방식

- `127.0.0.1:8765`에 작은 로컬 서버를 띄웁니다. 파일은 PC 밖으로 나가지 않습니다. 이미 켜져 있으면 브라우저 탭만 새로 엽니다.
- 파일이 있는 드라이브 기준으로 서빙해서 `../template/style.css` 같은 상대경로가 그대로 동작합니다.
- 저장 시 `<body>…</body>`만 교체합니다. `<head>`와 그 밖의 코드는 바이트 단위로 그대로입니다.
- 브라우저 확장 프로그램이 페이지에 붙인 요소는 저장에서 제외합니다.
- 저장·열기 요청은 실행마다 새로 만드는 토큰과 Host 헤더 검사로 다른 사이트의 접근을 막습니다.
- 최근 파일 목록: `%APPDATA%\html-simple-editor\recent.json`

## 파이썬으로 실행

의존성 없이 표준 라이브러리만 씁니다 (Python 3.10+).

```bash
pyw html_edit.py
```

## exe 빌드

```bash
python -m venv .venv
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --onefile --noconsole --name HTML편집 html_edit.py
```

## License

MIT
