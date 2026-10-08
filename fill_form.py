"""Serve an HTML form locally, fill it in the browser, save answers as JSON.

Each saved entry has: order, question, label, type, name, choices, answer.
  question = visible text asking for the answer (label text, or the text just
             before the field when the page has no <label>)
  label    = the real <label> text, or null if the field has none

Usage:
    python fill_form.py
Opens one browser page that starts on the bad form.
    F2  run Newform: convert the bad form into the good form and show it
    F8  go back to the bad form, filled in from data.json; then click Verify
        to check the old form's values still match data.json
    Submit on the good form: saves data.json, then after 1.5s returns to the old
    form filled in from it. Submit on the old form shows 'Submitted successfully'.
Newform needs: pip install beautifulsoup4 lxml. Stop the server with Ctrl+C.
"""
import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from html.parser import HTMLParser

SKIP_TYPES = {"submit", "button", "reset", "hidden", "image"}


def clean(text):
    return " ".join(text.split()) or None


class FormParser(HTMLParser):
    """Collect form fields in page order, with labels and nearby text."""

    def __init__(self):
        super().__init__()
        self.fields, self.labels = [], []  # labels: {"for", "text", "fields"}
        self.in_form = self.in_select = self.in_option = False
        self.skip_depth = 0  # inside script/style
        self.open_labels, self.last_text = [], None
        self.opt = None
        self.n = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.in_form = True
        elif tag in ("script", "style"):
            self.skip_depth += 1
        elif not self.in_form:
            return
        elif tag == "label":
            self.labels.append({"for": a.get("for"), "text": "", "fields": []})
            self.open_labels.append(self.labels[-1])
        elif tag == "option":
            self.in_option, self.opt = True, {"value": a.get("value"), "disabled": "disabled" in a, "text": ""}
        elif tag in ("input", "select", "textarea"):
            kind = tag if tag != "input" else (a.get("type") or "text").lower()
            if tag == "select":
                self.in_select = True
            if kind in SKIP_TYPES:
                return
            name = a.get("name") or a.get("id")
            key = name or f"#{self.n}"
            self.n += 1
            if kind == "radio":
                for f in self.fields:
                    if f["type"] == "radio" and f["name"] == name:
                        f["choices"].append(a.get("value"))
                        return
            field = {"order": len(self.fields) + 1, "question": None, "label": None,
                     "type": kind, "name": name, "id": a.get("id"),
                     "choices": [a.get("value")] if kind == "radio" else None,
                     "answer": None, "key": key, "_near": self.last_text}
            for lab in self.open_labels:
                lab["fields"].append(field)
            self.last_text = None
            self.fields.append(field)
            if tag == "select":
                field["choices"] = []
                self.cur_select = field

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False
        elif tag in ("script", "style"):
            self.skip_depth -= 1
        elif tag == "label" and self.open_labels:
            self.open_labels.pop()
        elif tag == "option" and self.opt:
            o = self.opt
            text = clean(o["text"])
            if text and not (o["disabled"] and o["value"] == ""):
                self.cur_select["choices"].append(text)
            self.in_option = False
            self.opt = None
        elif tag == "select":
            self.in_select = False

    def handle_data(self, data):
        if not self.in_form or self.skip_depth:
            return
        if self.in_option and self.opt is not None:
            self.opt["text"] += data
            return
        for lab in self.open_labels:
            lab["text"] += data
        if clean(data) and not self.open_labels:
            self.last_text = clean(data)


def extract_fields(html):
    p = FormParser()
    p.feed(html)
    if not p.labels and not p.fields and "<form" not in html.lower():
        raise SystemExit("No <form> found in the HTML file.")
    for f in p.fields:
        text = None
        for lab in p.labels:
            if f in lab["fields"] or (lab["for"] and lab["for"] == f["id"]):
                text = clean(lab["text"])
                break
        f["label"] = text
        f["question"] = text or f.pop("_near")
        f.pop("_near", None)
        f.pop("id")
    return p.fields


BAD_FILE = "bad_website/bad_website.html"
GOOD_FILE = "good_website/good_website.html"
FILES = {"bad": (BAD_FILE, "bad_data.json"), "good": (GOOD_FILE, "data.json")}

# Runs inside the form frame: collects answers, forwards key presses to the shell.
FRAME_JS = """
<script>
window.clControls = () => [...document.querySelectorAll('form input, form select, form textarea')]
  .filter(el => !['submit','button','reset','hidden','image'].includes(el.type));
window.clFill = function (values) {
  clControls().forEach((el, i) => { if (i < values.length && values[i] != null) el.value = values[i]; });
};
window.clMark = function (flags) {
  clControls().forEach((el, i) => { el.style.outline = flags[i] ? '3px solid #2a2' : '3px solid #c22'; });
};
window.clValues = () => clControls().map(el => el.value);
window.clCollect = function () {
  const answers = {};
  let n = 0;
  document.querySelectorAll('form input, form select, form textarea').forEach(el => {
    if (['submit','button','reset','hidden','image'].includes(el.type)) return;
    const k = el.name || el.id || '#' + n;
    n++;
    if (el.type === 'radio') { if (el.checked) answers[k] = el.value; }
    else if (el.type === 'checkbox') answers[k] = el.checked;
    else answers[k] = el.value;
  });
  return answers;
};
document.addEventListener('keydown', e => parent.clKey(e));
document.addEventListener('submit', e => { e.preventDefault(); parent.clSave(); });
</script>
"""

SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>ClearLabel</title>
<style>
  body { margin: 0; font: 15px sans-serif; display: flex; flex-direction: column; height: 100vh; }
  #bar { background: #222; color: #fff; padding: 8px 14px; display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
  #bar button { font: inherit; cursor: pointer; }
  #state { font-weight: bold; }
  #msg { margin-left: auto; color: #8cf; }
  iframe { flex: 1; border: 0; width: 100%; }
</style></head><body>
<div id="bar">
  <span id="state">BAD FORM</span>
  <button id="b-new">F2 &middot; Convert to good form</button>
  <button id="b-back">F8 &middot; Back to bad form (filled from data.json)</button>
  <button id="b-verify" hidden>Verify</button>
  <span id="msg"></span>
</div>
<iframe id="f" src="/form/bad"></iframe>
<script>
let current = 'bad';
async function goldRows() {
  const r = await fetch('/data/good');
  return r.ok ? await r.json() : null;
}
document.getElementById('f').addEventListener('load', async () => {
  if (!prefill) return;
  const rows = await goldRows();
  if (!rows) return msg('No data.json yet: fill in and submit the good form first.');
  f.contentWindow.clFill(rows.map(r => r.answer));
  msg('Old form filled from data.json. Click Verify.');
});
async function clVerify() {
  const rows = await goldRows();
  if (!rows) return msg('No data.json to verify against.');
  const now = f.contentWindow.clValues();
  const flags = rows.map((r, i) => String(now[i] ?? '') === String(r.answer ?? ''));
  f.contentWindow.clMark(flags);
  const bad = rows.filter((r, i) => !flags[i]).map(r => r.question);
  document.getElementById('state').textContent = bad.length ? 'NOT VERIFIED' : 'VERIFIED';
  msg(bad.length ? 'Mismatch: ' + bad.join(', ') : 'All ' + rows.length + ' answers match data.json');
}
const f = document.getElementById('f'), msg = t => document.getElementById('msg').textContent = t;
let prefill = false;
function show(key, fill) {
  current = key;
  prefill = !!fill;
  document.getElementById('b-verify').hidden = key !== 'bad' || !fill;
  f.src = '/form/' + key + '?t=' + Date.now();
  document.getElementById('state').textContent = key.toUpperCase() + ' FORM';
}
async function clConvert() {
  msg('Converting...');
  const r = await fetch('/convert', {method: 'POST'});
  const t = await r.text();
  if (r.ok) { show('good'); msg('Converted. Showing the good form.'); } else msg('Convert failed: ' + t);
}
async function clSave() {
  const answers = f.contentWindow.clCollect();
  const r = await fetch('/save?page=' + current, {method: 'POST', body: JSON.stringify(answers)});
  if (!r.ok) return msg('Save failed');
  const out = await r.text();
  const state = document.getElementById('state');
  if (current === 'good') {
    state.textContent = 'SAVED';
    msg('Answers saved to ' + out + '. Going back to the old form...');
    setTimeout(() => show('bad', true), 1500);
  } else {
    state.textContent = 'SUBMITTED';
    msg('Submitted successfully');
    document.getElementById('b-verify').hidden = true;
  }
}
function clKey(e) {  // F2 and F8 have no browser shortcut
  if (e.key === 'F2') { e.preventDefault(); clConvert(); }
  else if (e.key === 'F8') { e.preventDefault(); show('bad', true); msg(''); }
}
document.addEventListener('keydown', clKey);
document.getElementById('b-new').onclick = clConvert;
document.getElementById('b-back').onclick = () => { show('bad', true); msg(''); };
document.getElementById('b-verify').onclick = clVerify;
</script></body></html>
"""


def convert():
    """Run Newform: bad form -> good form. Returns an error string or None."""
    try:
        import Newform
    except ImportError as e:
        return f"{e} (run: pip install beautifulsoup4 lxml)"
    Path(GOOD_FILE).parent.mkdir(exist_ok=True)
    Newform.convert_bad_to_good(BAD_FILE, GOOD_FILE)
    return None if Path(GOOD_FILE).exists() else "Newform did not write the good form"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = ap.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def reply(self, body, code=200, ctype="text/plain; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                return self.reply(SHELL, ctype="text/html; charset=utf-8")
            key = path.rsplit("/", 1)[-1]
            if path.startswith("/form/") and key in FILES:
                try:
                    html = Path(FILES[key][0]).read_text(encoding="utf-8")
                except OSError as e:
                    return self.reply(f"Cannot read {FILES[key][0]}: {e}", 404)
                return self.reply(html + FRAME_JS, ctype="text/html; charset=utf-8")
            if path == "/data/good":
                try:
                    return self.reply(Path(FILES["good"][1]).read_text(encoding="utf-8"),
                                      ctype="application/json")
                except OSError:
                    return self.reply("no data.json yet", 404)
            self.reply("Not found", 404)

        def do_POST(self):
            path = self.path.split("?")[0]
            if path == "/convert":
                err = convert()
                return self.reply(err or "ok", 500 if err else 200)
            key = self.path.split("page=")[-1]
            answers = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            html_file, out = FILES[key]
            rows = extract_fields(Path(html_file).read_text(encoding="utf-8"))
            for f in rows:
                f["answer"] = answers.get(f.pop("key"))
            Path(out).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Saved {len(rows)} answers to {out}")
            self.reply(out)

        def log_message(self, *a):
            pass

    url = f"http://127.0.0.1:{args.port}"
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Running at {url}  (Ctrl+C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
