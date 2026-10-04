#!/usr/bin/env python3
"""Validate the PRD -> TRD -> tickets trail and print a safe implementation order.

Usage:
  check_trace.py --tickets .vibe/issues/<slug> [--prd docs/prd/<slug>.md]
                 [--trd docs/trd/<slug>.md] [--next] [--json]

Checks (exit 1 on any error): duplicate ticket ids, blocked_by/implements ids that
do not exist, dependency cycles, and Must requirements no ticket implements.
Warnings (exit 0): tickets that implement nothing, Must requirements missing from
the TRD, legacy tickets without an id. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^#{1,6}\s")
REQ_HEADING = re.compile(r"^#{2,6}\s+(R-\d+)\b")
PRIORITY = re.compile(r"^[\s*_>-]*priority[\s*_]*:[\s*_]*(must|should|could)\b", re.IGNORECASE)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _is_list_item(stripped: str) -> bool:
    return stripped == "-" or stripped.startswith("- ")


def parse_frontmatter(text: str) -> tuple[dict, list[str]]:
    """Parse the YAML subset agents write in ticket frontmatter. Returns (meta, errors).

    Supports ``key: value``, ``key: [a, b]``, block lists (``key:`` then ``- item`` lines) and
    folded/literal scalars (``key: >`` then indented text). Anything else is reported.
    """
    lines = text.lstrip("\ufeff").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or lines[0].strip() != "---":
        return {}, ["missing frontmatter (expected a leading '---' block)"]
    meta: dict = {}
    errors: list[str] = []
    current: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            return meta, errors
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current is not None and (line[0] in " \t" or _is_list_item(stripped)):
            value = meta[current]
            if _is_list_item(stripped):
                item = _unquote(stripped[1:].strip())
                if isinstance(value, list):
                    value.append(item)
                elif value == "":
                    meta[current] = [item]
                else:
                    errors.append(f"unexpected list item under {current!r}: {line!r}")
            elif isinstance(value, str):
                meta[current] = f"{value} {stripped}".strip()
            else:
                errors.append(f"unexpected continuation line under {current!r}: {line!r}")
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            errors.append(f"malformed frontmatter line: {line!r}")
            continue
        current = key.strip()
        value = value.strip()
        if value in {">", "|", ">-", "|-", ">+", "|+"}:
            meta[current] = ""
        elif value.startswith("[") and value.endswith("]"):
            meta[current] = [_unquote(v) for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[current] = _unquote(value)
    return meta, errors + ["unterminated frontmatter (missing closing '---')"]


def parse_prd(text: str) -> dict[str, str | None]:
    """Map requirement id -> priority ('must'|'should'|'could'|None)."""
    reqs: dict[str, str | None] = {}
    current: str | None = None
    for line in text.splitlines():
        match = REQ_HEADING.match(line)
        if match:
            current = match.group(1)
            reqs.setdefault(current, None)
        elif HEADING.match(line):
            current = None
        elif current and reqs[current] is None:
            priority = PRIORITY.match(line)
            if priority:
                reqs[current] = priority.group(1).lower()
    return reqs


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def load_tickets(directory: Path) -> tuple[list[dict], list[str]]:
    if not directory.is_dir():
        return [], [f"tickets directory not found: {directory}"]
    tickets: list[dict] = []
    errors: list[str] = []
    for path in sorted(directory.glob("issue-*.md")):
        meta, problems = parse_frontmatter(path.read_text(encoding="utf-8"))
        if problems:
            errors.extend(f"{path.name}: {p}" for p in problems)
            if not meta:
                continue
        ticket = dict(meta)
        ticket["file"] = path.name
        ticket["implements"] = _as_list(meta.get("implements"))
        ticket["blocked_by"] = _as_list(meta.get("blocked_by"))
        tickets.append(ticket)
    return tickets, errors


def _sort_key(ticket_id: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", ticket_id)), ticket_id


def check(reqs: dict[str, str | None] | None, tickets: list[dict], trd_text: str | None = None) -> Report:
    report = Report()
    by_id: dict[str, dict] = {}
    legacy: list[str] = []
    for ticket in tickets:
        tid = ticket.get("id")
        if not tid:
            legacy.append(ticket.get("file", "?"))
        elif tid in by_id:
            report.errors.append(f"duplicate ticket id {tid} ({by_id[tid].get('file')} and {ticket.get('file')})")
        else:
            by_id[tid] = ticket
    if legacy:
        report.warnings.append(
            f"{len(legacy)} ticket(s) have no id, traceability skipped for them: {', '.join(legacy)}"
        )

    for tid, ticket in by_id.items():
        for blocker in ticket.get("blocked_by", []):
            if blocker not in by_id:
                report.errors.append(f"{tid} ({ticket.get('file')}) is blocked_by unknown ticket {blocker}")
        if reqs is not None:
            for rid in ticket.get("implements", []):
                if rid not in reqs:
                    report.errors.append(f"{tid} ({ticket.get('file')}) implements unknown requirement {rid}")
            if not ticket.get("implements"):
                report.warnings.append(f"{tid} ({ticket.get('file')}) implements no requirement")

    if reqs is not None and by_id:
        implemented = {rid for t in by_id.values() for rid in t.get("implements", [])}
        for rid, priority in reqs.items():
            if priority == "must" and rid not in implemented:
                report.errors.append(f"Must requirement {rid} is not implemented by any ticket")
    if reqs is not None and trd_text is not None:
        for rid, priority in reqs.items():
            if priority == "must" and rid not in trd_text:
                report.warnings.append(f"{rid} (Must) is not mentioned in the TRD")

    remaining = {tid: {b for b in t.get("blocked_by", []) if b in by_id} for tid, t in by_id.items()}
    while remaining:
        ready = sorted((tid for tid, deps in remaining.items() if not deps), key=_sort_key)
        if not ready:
            report.errors.append(f"dependency cycle among: {', '.join(sorted(remaining, key=_sort_key))}")
            break
        chosen = ready[0]
        report.order.append(chosen)
        del remaining[chosen]
        for deps in remaining.values():
            deps.discard(chosen)
    return report


def next_ticket(tickets: list[dict], order: list[str]) -> str | None:
    """First ticket in *order* that is todo and whose blockers are all done."""
    status = {t["id"]: str(t.get("status", "todo")).lower() for t in tickets if t.get("id")}
    by_id = {t["id"]: t for t in tickets if t.get("id")}
    for tid in order:
        blockers = by_id[tid].get("blocked_by", [])
        if status[tid] == "todo" and all(status.get(b) == "done" for b in blockers):
            return tid
    return None


def _read(path: str, label: str, errors: list[str]) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read {label} {path}: {exc.strerror or exc}")
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the PRD -> TRD -> tickets trail.")
    parser.add_argument("--tickets", required=True, help="directory holding issue-NN.md files")
    parser.add_argument("--prd", help="PRD file (enables requirement checks)")
    parser.add_argument("--trd", help="TRD file (warns when a Must requirement is missing)")
    parser.add_argument("--next", action="store_true", help="print the next ready ticket id")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    tickets, errors = load_tickets(Path(args.tickets))
    reqs = trd_text = None
    if args.prd:
        prd_text = _read(args.prd, "PRD", errors)
        reqs = parse_prd(prd_text) if prd_text is not None else None
        if reqs is not None and not reqs:
            # An unparsable PRD would otherwise make every ticket look wrong.
            errors.append(f"no '### R-NNN' requirement headings found in {args.prd}")
            reqs = None
    if args.trd:
        trd_text = _read(args.trd, "TRD", errors)
    report = check(reqs, tickets, trd_text)
    report.errors = errors + report.errors
    upcoming = None if report.errors else next_ticket(tickets, report.order)

    if args.json:
        print(json.dumps({"errors": report.errors, "warnings": report.warnings, "order": report.order, "next": upcoming}))
    elif args.next and not report.errors:
        stuck = [t["id"] for t in tickets if t.get("id") and str(t.get("status", "")).lower() == "in-progress"]
        print(upcoming or ("none" + (f" (in-progress: {', '.join(stuck)})" if stuck else "")))
    else:
        for label, items in (("errors", report.errors), ("warnings", report.warnings)):
            if items:
                print(f"{label}:")
                print("\n".join(f"  - {item}" for item in items))
        print("order: " + (" -> ".join(report.order) if report.order else "(none)"))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
