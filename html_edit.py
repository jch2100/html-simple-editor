"""Edit HTML text in the browser: click text, type, Enter = <br>, Ctrl+S saves.

Usage:
  pyw html_edit.py            start page ([열기] button + recent files)
  pyw html_edit.py FILE.html  open FILE directly in edit mode

One server per PC on 127.0.0.1:8765; a second launch just opens a browser tab.
Only the <body>...</body> region is replaced on save, so <head> stays
byte-identical. The previous version is kept as <file>.bak.
"""
import html
import http.server
import json
import os
import pathlib
import re
import secrets
import shutil
import sys
import threading
import urllib.parse
import webbrowser

PORT = int(os.environ.get('HTML_SIMPLE_EDITOR_PORT', 8765))
HOST = f'127.0.0.1:{PORT}'
# Per-user state lives outside the program folder so a packaged exe works too.
APP_DIR = pathlib.Path(os.environ.get('APPDATA') or pathlib.Path.home()) / 'html-simple-editor'
RECENT_FILE = APP_DIR / 'recent.json'
DEFAULT_DIR = pathlib.Path.home() / 'Documents'
TOKEN = secrets.token_urlsafe(16)
HTML_EXT = ('.html', '.htm')

COMMON_JS = r"""
async function heOpen(t, status) {
  status('파일 선택 창을 확인하세요 (브라우저 뒤에 있을 수 있어요)');
  try {
    const res = await fetch('/__open?t=' + t, { method: 'POST' });
    const data = await res.json();
    if (data.url) { location.href = data.url; return; }
    status(data.error || '');
  } catch (err) {
    status('열기 실패: ' + err.message);
  }
}
async function heQuit(t) {
  await fetch('/__quit?t=' + t, { method: 'POST' }).catch(() => {});
  document.title = '편집기 꺼짐';
  document.documentElement.innerHTML =
    '<body style="font:16px system-ui,sans-serif;padding:40px">편집기를 껐습니다. 이 탭을 닫아도 됩니다.</body>';
}
"""

EDITOR_JS = r"""
(() => {
  const T = '__TOKEN__';
  const body = document.body;
  // Top-level elements present at load; anything appended later at the top
  // level (browser extensions do this) is dropped on save.
  const originalTop = new Set(body.children);
  body.contentEditable = 'true';
  let dirty = false;

  // Take keys before the page's own scripts. Slide decks bind window keydown
  // (space = next slide, arrows = move) and would swallow plain typing.
  const onKey = (e) => {
    if (!body.contains(e.target)) return;  // toolbar and outside: leave alone
    if (e.type === 'keydown') {
      // Plain Enter -> <br> instead of splitting the block into a new <div>/<p>.
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        document.execCommand('insertLineBreak');
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        save();
      }
    }
    e.stopPropagation();
  };
  ['keydown', 'keypress', 'keyup'].forEach((t) => window.addEventListener(t, onKey, true));
  // Fallback for Enter pressed while the Korean IME was composing. Chrome
  // ignores execCommand re-entered from beforeinput, so defer it a tick.
  document.addEventListener('beforeinput', (e) => {
    if (e.inputType === 'insertParagraph') {
      e.preventDefault();
      setTimeout(() => document.execCommand('insertLineBreak'));
    }
  });
  // Paste as plain text so no foreign styling leaks into the file.
  document.addEventListener('paste', (e) => {
    e.preventDefault();
    document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
  });
  document.addEventListener('input', () => {
    dirty = true;
    status('수정됨 · Ctrl+S로 저장');
  });
  window.addEventListener('beforeunload', (e) => { if (dirty) e.preventDefault(); });

  // Toolbar lives in a shadow root outside <body>: page CSS can't reach it
  // and it never ends up in the saved file.
  const host = document.createElement('div');
  host.id = '__html_edit_bar';
  host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;';
  const printStyle = document.createElement('style');
  printStyle.textContent = '@media print{#__html_edit_bar{display:none!important}}';
  document.head.appendChild(printStyle);
  const ui = host.attachShadow({ mode: 'open' });
  ui.innerHTML = `<style>
    .bar{display:flex;gap:8px;align-items:center;padding:8px 10px;border-radius:10px;
      background:#1f2328;color:#fff;font:13px/1.4 system-ui,sans-serif;
      box-shadow:0 4px 14px rgba(0,0,0,.25)}
    .status{padding:0 4px;white-space:nowrap}
    .status[data-tone=ok]{color:#7ee2a8}
    .status[data-tone=err]{color:#ff9b9b}
    button{font:inherit;color:#fff;background:#3a4048;border:0;border-radius:6px;
      padding:5px 10px;cursor:pointer}
    button:hover{background:#4a515b}
  </style>
  <div class="bar"><span class="status"></span>
    <button data-act="open">다른 파일 열기</button><button data-act="quit">끄기</button></div>`;
  document.documentElement.appendChild(host);
  const statusEl = ui.querySelector('.status');
  function status(msg, tone) {
    statusEl.textContent = msg;
    statusEl.dataset.tone = tone || '';
  }
  ui.addEventListener('click', (e) => {
    const act = e.target.dataset && e.target.dataset.act;
    if (act === 'open') heOpen(T, status);
    if (act === 'quit' && (!dirty || confirm('저장하지 않은 수정이 있습니다. 그래도 끌까요?'))) {
      dirty = false;
      heQuit(T);
    }
  });

  async function save() {
    const clone = body.cloneNode(true);
    clone.removeAttribute('contenteditable');
    const injected = [...body.children]
      .map((el, i) => (originalTop.has(el) && el.id !== '__html_edit' ? null : clone.children[i]))
      .filter(Boolean);
    injected.forEach((n) => n.remove());
    clone.querySelectorAll('[src^="chrome-extension:"], [href^="chrome-extension:"]').forEach((n) => n.remove());
    try {
      const res = await fetch('/__save?t=' + T + '&path=' + encodeURIComponent(location.pathname), {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        body: clone.outerHTML,
      });
      if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
      dirty = false;
      status('저장됨 ' + new Date().toTimeString().slice(0, 5), 'ok');
    } catch (err) {
      status('저장 실패: ' + err.message, 'err');
    }
  }

  // Pages that build or change their own DOM (slide decks, dashboards) save
  // whatever is on screen right now, so warn before the first Ctrl+S.
  const pageScripts = [...document.scripts].filter((s) => s.id !== '__html_edit').length;
  status(pageScripts
    ? '편집 모드 · 스크립트가 있는 파일: 저장하면 화면 상태가 굳습니다'
    : '편집 모드 · Enter = 줄바꿈 · Ctrl+S = 저장');
})();
"""

START_HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HTML 편집</title>
<style>
  body{margin:0;background:#f4f5f7;color:#1f2328;font:15px/1.6 system-ui,"Malgun Gothic",sans-serif}
  main{max-width:640px;margin:0 auto;padding:64px 20px}
  h1{margin:0 0 4px;font-size:28px}
  .sub{margin:0 0 28px;color:#59636e}
  .primary{font:inherit;font-size:17px;font-weight:600;color:#fff;background:#1f6feb;border:0;
    border-radius:10px;padding:14px 36px;cursor:pointer}
  .primary:hover{background:#1a5fcc}
  .status{min-height:1.6em;margin:12px 0 32px;color:#59636e}
  h2{margin:0 0 8px;font-size:14px;color:#59636e;font-weight:600}
  ul{list-style:none;margin:0 0 40px;padding:0;background:#fff;border:1px solid #d8dde3;border-radius:10px}
  li+li{border-top:1px solid #eaeef2}
  li a{display:block;padding:12px 16px;color:inherit;text-decoration:none}
  li a:hover{background:#f0f5ff}
  li b{display:block;font-weight:600}
  li small{display:block;color:#6e7781;overflow-wrap:anywhere}
  li.empty{padding:12px 16px;color:#6e7781}
  .link{font:inherit;color:#59636e;background:none;border:0;padding:0;cursor:pointer;text-decoration:underline}
</style></head>
<body><main>
  <h1>HTML 편집</h1>
  <p class="sub">화면에서 글자를 고치고 Ctrl+S로 원본 파일에 저장합니다.</p>
  <button id="open" class="primary">열기</button>
  <p id="status" class="status"></p>
  <h2>최근 파일</h2>
  <ul>__RECENT__</ul>
  <button id="quit" class="link">편집기 끄기</button>
</main>
<script>
__COMMON__
const T = '__TOKEN__';
const status = (msg) => { document.getElementById('status').textContent = msg; };
document.getElementById('open').addEventListener('click', () => heOpen(T, status));
document.getElementById('quit').addEventListener('click', () => heQuit(T));
</script>
</body></html>
"""


def to_url(path):
    """C:\\a\\b.html -> /fs/C/a/b.html (keeps relative assets resolvable)."""
    path = pathlib.Path(path).resolve()
    drive = path.drive.rstrip(':')
    if len(drive) != 1:
        raise ValueError(f'unsupported path: {path}')
    return f'/fs/{drive}/' + urllib.parse.quote(path.relative_to(path.anchor).as_posix())


def from_url(url_path):
    m = re.match(r'/fs/([A-Za-z])/(.*)$', urllib.parse.unquote(url_path))
    return pathlib.Path(f'{m[1]}:/', m[2]) if m else None


def load_recent():
    try:
        items = json.loads(RECENT_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [p for p in items if pathlib.Path(p).is_file()]


def add_recent(path):
    items = [str(path)] + [p for p in load_recent() if p != str(path)]
    RECENT_FILE.write_text(json.dumps(items[:5], ensure_ascii=False, indent=1), encoding='utf-8')


def start_page():
    rows = ''.join(
        f'<li><a href="{to_url(p)}?edit"><b>{html.escape(pathlib.Path(p).name)}</b>'
        f'<small>{html.escape(str(pathlib.Path(p).parent))}</small></a></li>'
        for p in load_recent()
    ) or '<li class="empty">아직 연 파일이 없습니다</li>'
    return START_HTML.replace('__COMMON__', COMMON_JS).replace('__TOKEN__', TOKEN).replace('__RECENT__', rows)


def inject(page):
    js = COMMON_JS + EDITOR_JS.replace('__TOKEN__', TOKEN)
    tag = '<script id="__html_edit">' + js + '</script>'
    idx = page.lower().rfind('</body>')
    return page[:idx] + tag + page[idx:] if idx != -1 else page + tag


def save(target, new_body):
    raw = target.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    original = raw.decode('utf-8-sig')
    start = re.search(r'<body\b', original, re.I)
    end = original.lower().rfind('</body>')
    if not start or end == -1:
        raise ValueError('no <body>...</body> in file')
    # The parser moves whitespace after </body> into the body; restore the
    # original whitespace before </body> so repeated saves don't add lines.
    orig_ws = re.search(r'\s*$', original[:end]).group()
    new_body = re.sub(r'\s*</body>\s*$', lambda _: orig_ws + '</body>', new_body, flags=re.I)
    updated = original[:start.start()] + new_body + original[end + len('</body>'):]
    if '\r\n' in original:
        updated = updated.replace('\r\n', '\n').replace('\n', '\r\n')
    shutil.copy2(target, target.with_name(target.name + '.bak'))
    target.write_bytes((b'\xef\xbb\xbf' if bom else b'') + updated.encode('utf-8'))


dialog_lock = threading.Lock()


def pick_file():
    import tkinter as tk
    from tkinter import filedialog
    recent = load_recent()
    initial = pathlib.Path(recent[0]).parent if recent else DEFAULT_DIR
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        return filedialog.askopenfilename(
            parent=root, title='HTML 파일 열기', initialdir=str(initial),
            filetypes=[('HTML 파일', '*.html *.htm')])
    finally:
        root.destroy()


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def host_ok(self):
        # Reject DNS-rebinding requests from other sites.
        return self.headers.get('Host') == HOST

    def send_bytes(self, data, ctype, code=200):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj):
        self.send_bytes(json.dumps(obj).encode(), 'application/json')

    def translate_path(self, path):
        real = from_url(urllib.parse.urlsplit(path).path)
        return str(real) if real else str(APP_DIR / '__not_found__')

    def do_GET(self):
        if not self.host_ok():
            return self.send_error(403)
        url = urllib.parse.urlsplit(self.path)
        if url.path == '/':
            return self.send_bytes(start_page().encode('utf-8'), 'text/html; charset=utf-8')
        path = from_url(url.path)
        if path and url.query == 'edit':
            if path.suffix.lower() not in HTML_EXT or not path.is_file():
                return self.send_error(404)
            add_recent(path)
            page = inject(path.read_bytes().decode('utf-8-sig'))
            return self.send_bytes(page.encode('utf-8'), 'text/html; charset=utf-8')
        super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        if not self.host_ok() or query.get('t') != [TOKEN]:
            return self.send_error(403)
        if url.path == '/__open':
            if not dialog_lock.acquire(blocking=False):
                return self.send_json({'error': '파일 선택 창이 이미 열려 있습니다'})
            try:
                picked = pick_file()
            finally:
                dialog_lock.release()
            return self.send_json({'url': to_url(picked) + '?edit'} if picked else {})
        if url.path == '/__save':
            path = from_url(query.get('path', [''])[0])
            if not path or path.suffix.lower() not in HTML_EXT or not path.is_file():
                return self.send_error(400)
            data = self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8')
            try:
                save(path, data)
            except Exception as err:
                return self.send_error(500, str(err))
            self.send_response(204)
            self.end_headers()
            return
        if url.path == '/__quit':
            self.send_response(204)
            self.end_headers()
            threading.Thread(target=self.server.shutdown).start()
            return
        self.send_error(404)


class Server(http.server.ThreadingHTTPServer):
    # On Windows, address reuse would let a second instance share the port.
    allow_reuse_address = False
    daemon_threads = True


def main():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if sys.stderr is None:  # pythonw / windowed exe has no console
        sys.stdout = sys.stderr = open(APP_DIR / 'html_edit.log', 'a', encoding='utf-8')
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    url = f'http://{HOST}/'
    if args:
        target = pathlib.Path(args[0]).resolve()
        if target.suffix.lower() in HTML_EXT and target.is_file():
            url = f'http://{HOST}' + to_url(target) + '?edit'
    try:
        server = Server(('127.0.0.1', PORT), Handler)
    except OSError:
        server = None  # already running: just open a tab on it
    if '--no-open' not in sys.argv:
        webbrowser.open(url)
    if server:
        server.serve_forever()


if __name__ == '__main__':
    main()
