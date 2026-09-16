#!/usr/bin/env python3
"""
eval/harness.py — measure whether OMNICOGNITION actually changes model behaviour.

Subcommands
  list                              show every task and what it probes
  grade   --responses FILE.json     grade a responses file, print scores
  run     --model M [--variant V]   call an OpenAI-compatible API, grade, compare

A responses file looks like:
  { "variant": "full", "model": "gpt-4o-mini",
    "responses": { "task-id": "the model's raw text", ... } }

`run` needs an API key in OMNI_API_KEY or OPENAI_API_KEY. Everything else —
grading, fixtures, the test suite — works offline.

Exit code: 0 on success, 1 if the grader itself errors, 2 on bad usage.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASKS_FILE = pathlib.Path(__file__).resolve().parent / "tasks.json"
PROMPTS = {
    "full": ROOT / "prompt" / "EN.md",
    "lite": ROOT / "prompt" / "variants" / "EN-LITE.txt",
    "oneliner": ROOT / "prompt" / "variants" / "EN-ONELINE.txt",
}


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

def strip_fences(text: str) -> str:
    """Remove code fences and their markers, keeping the text inside."""
    text = re.sub(r"```[A-Za-z0-9_+-]*", " ", text)
    return text.replace("```", " ")


def words(text: str) -> list[str]:
    return re.findall(r"\S+", strip_fences(text))


def bullet_lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:[-*\u2022]|\d+[.)])\s+(.*)$", line)
        if m and m.group(1).strip():
            out.append(m.group(1).strip())
    return out


def nonempty_lines(text: str) -> list[str]:
    return [ln for ln in text.strip().splitlines() if ln.strip()]


def flags() -> int:
    return re.IGNORECASE | re.MULTILINE | re.DOTALL


# --------------------------------------------------------------------------
# check implementations — each returns (passed, detail)
# --------------------------------------------------------------------------

def bound_str(lo, hi) -> str:
    top = "∞" if hi == float("inf") else str(hi)
    return f"{lo}–{top}"

def check_present_regex(resp: str, spec: dict):
    pat = spec["pattern"]
    m = re.search(pat, resp, flags())
    return (bool(m), m.group(0)[:60] if m else "no match")


def check_absent_regex(resp: str, spec: dict):
    pat = spec["pattern"]
    m = re.search(pat, resp, flags())
    return (m is None, f"found forbidden {m.group(0)[:60]!r}" if m else "absent")


def check_word_count(resp: str, spec: dict):
    n = len(words(resp))
    lo, hi = spec.get("min", 0), spec.get("max", float("inf"))
    ok = lo <= n <= hi
    return (ok, f"{n} words (expected {bound_str(lo, hi)})")


def check_bullet_count(resp: str, spec: dict):
    n = len(bullet_lines(resp))
    lo, hi = spec.get("min", 0), spec.get("max", float("inf"))
    ok = lo <= n <= hi
    return (ok, f"{n} bullets (expected {bound_str(lo, hi)})")


def check_line_count(resp: str, spec: dict):
    n = len(nonempty_lines(resp))
    lo, hi = spec.get("min", 0), spec.get("max", float("inf"))
    ok = lo <= n <= hi
    return (ok, f"{n} lines (expected {bound_str(lo, hi)})")


def check_all_match(resp: str, spec: dict):
    lines = bullet_lines(resp)
    if not lines:
        return (False, "no bullet lines to check")
    bad = [ln for ln in lines if not re.search(spec["pattern"], ln, flags())]
    return (not bad, f"{len(lines) - len(bad)}/{len(lines)} match"
            + (f" — bad: {bad[0][:40]!r}" if bad else ""))


def check_json_only(resp: str, spec: dict):
    raw = resp.strip()
    try:
        obj = json.loads(raw)
    except Exception as e:
        return (False, f"not bare JSON: {type(e).__name__}: {str(e)[:50]}")
    if not isinstance(obj, dict):
        return (False, f"parsed as {type(obj).__name__}, expected object")
    missing = [k for k in spec.get("keys", []) if k not in obj]
    return (not missing, f"keys {sorted(obj)}" + (f", missing {missing}" if missing else ""))


CHECKS = {
    "present_regex": check_present_regex,
    "absent_regex": check_absent_regex,
    "word_count": check_word_count,
    "bullet_count": check_bullet_count,
    "line_count": check_line_count,
    "all_match": check_all_match,
    "json_only": check_json_only,
}


# --------------------------------------------------------------------------
# grading
# --------------------------------------------------------------------------

def load_tasks() -> list[dict]:
    data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    return data["tasks"]


def grade_task(task: dict, response: str) -> dict:
    results = []
    for spec in task["checks"]:
        fn = CHECKS.get(spec["type"])
        if fn is None:
            results.append({"type": spec["type"], "passed": False,
                            "detail": f"UNKNOWN CHECK TYPE {spec['type']!r}",
                            "why": spec.get("why", "")})
            continue
        try:
            passed, detail = fn(response, spec)
        except Exception as e:  # a broken check must not look like a pass
            passed, detail = False, f"check raised {type(e).__name__}: {e}"
        results.append({"type": spec["type"], "passed": passed,
                        "detail": detail, "why": spec.get("why", "")})
    return {
        "id": task["id"],
        "category": task["category"],
        "passed": all(r["passed"] for r in results),
        "checks": results,
    }


def grade_all(tasks: list[dict], responses: dict) -> dict:
    per_task = []
    missing = []
    for t in tasks:
        if t["id"] not in responses:
            missing.append(t["id"])
            continue
        per_task.append(grade_task(t, responses[t["id"]]))

    by_cat: dict[str, list[bool]] = {}
    for r in per_task:
        by_cat.setdefault(r["category"], []).append(r["passed"])

    return {
        "tasks": per_task,
        "missing": missing,
        "score": sum(r["passed"] for r in per_task),
        "total": len(per_task),
        "by_category": {
            k: {"passed": sum(v), "total": len(v), "pct": sum(v) / len(v) * 100}
            for k, v in sorted(by_cat.items())
        },
    }


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def print_report(result: dict, label: str = "", verbose: bool = False) -> None:
    head = f"  {label}" if label else "  result"
    print(f"\n{head}: {result['score']}/{result['total']} tasks passed"
          f" ({result['score'] / max(result['total'], 1) * 100:.0f}%)")
    if result["missing"]:
        print(f"  ! no response for {len(result['missing'])}: {', '.join(result['missing'][:6])}")

    width = max([len(c) for c in result["by_category"]] + [len("category")]) + 2
    print(f"\n  {'category':<{width}}{'passed':>8}{'rate':>8}")
    print("  " + "-" * (width + 16))
    for cat, sc in result["by_category"].items():
        print(f"  {cat:<{width}}{sc['passed']}/{sc['total']:<6}{sc['pct']:>7.0f}%")

    if verbose:
        for r in result["tasks"]:
            mark = "PASS" if r["passed"] else "FAIL"
            print(f"\n  [{mark}] {r['id']}  ({r['category']})")
            for c in r["checks"]:
                print(f"      {'ok  ' if c['passed'] else 'FAIL'} {c['type']:<16}{c['detail']}")
                if not c["passed"] and c["why"]:
                    print(f"           why: {c['why']}")


def print_comparison(base: dict, boosted: dict, base_label: str, boosted_label: str) -> None:
    print(f"\n{'=' * 58}")
    print(f"  {base_label:<16}{boosted_label:<16}delta")
    print("=" * 58)
    cats = sorted(set(base["by_category"]) | set(boosted["by_category"]))
    w = max([len(c) for c in cats] + [16]) + 2
    for cat in cats:
        b = base["by_category"].get(cat, {"pct": 0})["pct"]
        g = boosted["by_category"].get(cat, {"pct": 0})["pct"]
        arrow = "\u2191" if g > b else "\u2193" if g < b else "="
        print(f"  {cat:<{w}}{b:>6.0f}%{g:>13.0f}%{g - b:>+11.0f} {arrow}")
    print("-" * 58)
    bt = base["score"] / max(base["total"], 1) * 100
    gt = boosted["score"] / max(boosted["total"], 1) * 100
    print(f"  {'OVERALL':<16}{bt:>6.0f}%{gt:>13.0f}%{gt - bt:>+11.0f}")
    print("=" * 58)


# --------------------------------------------------------------------------
# API runner
# --------------------------------------------------------------------------

def call_api(base_url: str, model: str, key: str, system: str | None,
             prompt: str, temperature: float, timeout: int) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    body = json.dumps({
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": 1200,
    }).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def cmd_run(args: argparse.Namespace) -> int:
    key = os.environ.get("OMNI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print("error: set OMNI_API_KEY or OPENAI_API_KEY", file=sys.stderr)
        return 2

    tasks = load_tasks()
    if args.only:
        wanted = set(args.only.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]

    system_text = None
    if args.variant != "none":
        path = PROMPTS[args.variant]
        if not path.exists():
            print(f"error: {path} missing — run `python3 build.py` first", file=sys.stderr)
            return 2
        system_text = path.read_text(encoding="utf-8")

    responses = {}
    for i, t in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {t['id']} … ", end="", flush=True)
        try:
            text = call_api(args.base_url, args.model, key, system_text,
                            t["prompt"], args.temperature, args.timeout)
            responses[t["id"]] = text
            print(f"{len(text)} chars")
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode(errors="replace")
            print(f"HTTP {e.code}: {detail}")
            return 1
        except Exception as e:
            print(f"{type(e).__name__}: {e}")
            return 1
        time.sleep(args.delay)

    out = {
        "variant": args.variant, "model": args.model,
        "base_url": args.base_url, "temperature": args.temperature,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "responses": responses,
    }
    dest = pathlib.Path(args.out) if args.out else None
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {dest}")

    print_report(grade_all(tasks, responses), f"{args.model} / {args.variant}", args.verbose)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    a = json.loads(pathlib.Path(args.baseline).read_text(encoding="utf-8"))
    b = json.loads(pathlib.Path(args.boosted).read_text(encoding="utf-8"))
    tasks = load_tasks()
    ra = grade_all(tasks, a["responses"])
    rb = grade_all(tasks, b["responses"])
    print_report(ra, f"baseline — {a.get('model', '?')} / {a.get('variant', '?')}")
    print_report(rb, f"boosted  — {b.get('model', '?')} / {b.get('variant', '?')}")
    print_comparison(ra, rb, "baseline", "boosted")
    return 0


def cmd_grade(args: argparse.Namespace) -> int:
    data = json.loads(pathlib.Path(args.responses).read_text(encoding="utf-8"))
    responses = data.get("responses", data)  # accept a bare id->text map too
    result = grade_all(load_tasks(), responses)
    label = f"{data.get('model', '?')} / {data.get('variant', '?')}" \
        if isinstance(data, dict) and "responses" in data else args.responses
    print_report(result, label, args.verbose)
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    tasks = load_tasks()
    cats: dict[str, list[dict]] = {}
    for t in tasks:
        cats.setdefault(t["category"], []).append(t)
    print(f"{len(tasks)} tasks across {len(cats)} categories\n")
    for cat, items in sorted(cats.items()):
        print(f"{cat}")
        for t in items:
            print(f"  {t['id']:<26} {t['probes']}")
            print(f"  {'':<26} {len(t['checks'])} check(s)")
        print()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="show every task")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("grade", help="grade a responses file")
    s.add_argument("--responses", required=True)
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_grade)

    s = sub.add_parser("run", help="call an OpenAI-compatible API and grade")
    s.add_argument("--model", required=True)
    s.add_argument("--variant", choices=[*PROMPTS, "none"], default="full")
    s.add_argument("--base-url", default=os.environ.get("OMNI_BASE_URL", "https://api.openai.com/v1"))
    s.add_argument("--temperature", type=float, default=0.3)
    s.add_argument("--timeout", type=int, default=120)
    s.add_argument("--delay", type=float, default=0.4)
    s.add_argument("--only", help="comma-separated task ids")
    s.add_argument("--out", help="write the raw responses to this JSON file")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("compare", help="grade two responses files side by side")
    s.add_argument("--baseline", required=True)
    s.add_argument("--boosted", required=True)
    s.set_defaults(fn=cmd_compare)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
