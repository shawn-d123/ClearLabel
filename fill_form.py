"""Serve an HTML form locally, fill it in the browser, save answers as JSON.

Each saved entry has: order, question, label, type, name, choices, answer.
  question = visible text asking for the answer (label text, or the text just
             before the field when the page has no <label>)
  label    = the real <label> text, or null if the field has none

Usage:
    python fill_form.py
Opens the bad website at http://127.0.0.1:8000. A bar at the bottom of each page
has a link to switch to the other version and a button that fills in the form
answers and saves them: good form -> data.json, bad form -> bad_data.json.
Submitting the form does the same. Stop with Ctrl+C.
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


INJECT = """
<div id="cl-bar" style="position:fixed;bottom:0;left:0;right:0;padding:8px 12px;background:#222;color:#fff;font:14px sans-serif;display:flex;gap:12px;align-items:center">
  <a href="__OTHER_URL__" style="color:#8cf">__OTHER_TEXT__</a>
  <button type="button" id="cl-fill">Fill form &amp; save to __OUT__</button>
  <span id="cl-status"></span>
</div>
<script>
async function clSave() {
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
  const r = await fetch('/save?page=__PAGE__', {method: 'POST', body: JSON.stringify(answers)});
  document.getElementById('cl-status').textContent = r.ok ? 'Saved to __OUT__' : 'Save failed';
}
document.getElementById('cl-fill').addEventListener('click', clSave);
document.querySelector('form').addEventListener('submit', e => { e.preventDefault(); clSave(); });
</script>
"""

# page key -> (url, html file, output json, link to the other page)
PAGES = {
    "bad": ("/", "bad_website/bad_website.html", "bad_data.json", "/good", "Switch to the good form"),
    "good": ("/good", "good_website/good_website.html", "data.json", "/", "Switch to the bad form"),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = ap.parse_args()

    pages, fields = {}, {}
    for key, (url, html_file, out, other_url, other_text) in PAGES.items():
        html = Path(html_file).read_text(encoding="utf-8")
        fields[key] = extract_fields(html)
        bar = (INJECT.replace("__OTHER_URL__", other_url).replace("__OTHER_TEXT__", other_text)
               .replace("__OUT__", out).replace("__PAGE__", key))
        pages[url] = (html + bar).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            page = pages.get(self.path.split("?")[0])
            self.send_response(200 if page else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page or b"Not found")

        def do_POST(self):
            key = self.path.split("page=")[-1]
            answers = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            rows = fields[key]
            for f in rows:
                f["answer"] = answers.get(f["key"])
            out = Path(PAGES[key][2])
            out.write_text(json.dumps([{k: v for k, v in f.items() if k != "key"} for f in rows],
                                      indent=2, ensure_ascii=False), encoding="utf-8")
            self.send_response(200)
            self.end_headers()
            print(f"Saved {len(rows)} answers to {out}")

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
