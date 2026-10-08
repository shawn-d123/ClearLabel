"""Turn inbox JSON into structured question / label / choices records.

Assumed input (a list, or an object with an "emails"/"messages"/"items" list;
a file can also hold several inboxes as {"inbox_name": [...], ...}):

    {"id": "1", "from": "a@b.com", "subject": "...", "body": "...",
     "label": "promotions"}            # "labels": [...] also accepted

Output: JSON list of records:

    {"id", "inbox", "question", "context": {from, subject, body},
     "label", "choices"}

Usage:
    python restructuring.py inbox1.json inbox2.json -o structured.json
"""
import argparse
import json
from pathlib import Path

LIST_KEYS = ("emails", "messages", "items", "inbox")
QUESTION = "Which category best fits this email?"


def find_records(data, name):
    """Yield (inbox_name, record) pairs from the various assumed layouts."""
    if isinstance(data, list):
        for rec in data:
            yield name, rec
    elif isinstance(data, dict):
        for key in LIST_KEYS:
            if isinstance(data.get(key), list):
                yield from find_records(data[key], name)
                return
        # {"inbox_name": [...]} layout
        for key, val in data.items():
            if isinstance(val, list):
                yield from find_records(val, key)


def get_label(rec):
    label = rec.get("label")
    if label is None and rec.get("labels"):
        label = rec["labels"][0] if isinstance(rec["labels"], list) else rec["labels"]
    return label


def restructure(paths):
    rows = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for inbox, rec in find_records(data, Path(path).stem):
            if not isinstance(rec, dict):
                continue
            rows.append({
                "id": rec.get("id", f"{inbox}-{len(rows)}"),
                "inbox": inbox,
                "question": QUESTION,
                "context": {
                    "from": rec.get("from") or rec.get("sender"),
                    "subject": rec.get("subject"),
                    "body": rec.get("body") or rec.get("text") or rec.get("snippet"),
                },
                "label": get_label(rec),
            })
    choices = sorted({r["label"] for r in rows if r["label"]})
    for r in rows:
        r["choices"] = choices
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="+", help="inbox JSON files")
    ap.add_argument("-o", "--output", default="structured.json")
    args = ap.parse_args()
    rows = restructure(args.inputs)
    Path(args.output).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} records to {args.output}")


if __name__ == "__main__":
    main()
