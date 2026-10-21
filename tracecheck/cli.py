import argparse
import json
from datetime import date
from pathlib import Path

from tracecheck.engine import load_rfq, load_store, run_gate

EXIT_CODES = {"RELEASED": 0, "AWAITING_REVIEW": 1, "BLOCKED": 2}


def format_table(report):
    rows = [("LINE", "PART NUMBER", "DECISION", "REASON")]
    for line in report["lines"]:
        decision = line["decision"] + (" (approved)" if line["override"] else "")
        rows.append((line["line_id"], line["part_number"], decision, line["reason"]))
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    out = []
    for i, r in enumerate(rows):
        out.append("  ".join(c.ljust(w) for c, w in zip(r[:3], widths)) + "  " + r[3])
        if i == 0:
            out.append("  ".join("-" * w for w in widths) + "  " + "-" * 6)
    s = report["summary"]
    out.append("")
    out.append(f"{s['PASS']} pass, {s['HOLD']} hold, {s['BLOCK']} block (as of {report['as_of']})")
    messages = {
        "RELEASED": "QUOTE RELEASED: every line is traceable.",
        "AWAITING_REVIEW": "QUOTE HELD: approve or fix the HOLD lines before release.",
        "BLOCKED": "QUOTE NOT RELEASED: fix the BLOCK lines; blocks cannot be overridden.",
    }
    out.append(messages[report["status"]])
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tracecheck", description="Trace-before-bid quote gate")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="check an RFQ against the supplier document store")
    run.add_argument("rfq", help="RFQ CSV file")
    run.add_argument("--docs", help="document store directory (default: docs/ next to the RFQ)")
    run.add_argument("--as-of", type=date.fromisoformat, default=date.today(),
                     help="check date, YYYY-MM-DD (default: today)")
    run.add_argument("--approve", action="append", default=[], metavar="LINE_ID",
                     help="human approval for a HOLD line (repeatable)")
    run.add_argument("--reviewer", help="name logged with approvals")
    run.add_argument("--json-out", help="also write the JSON report to this file")
    args = parser.parse_args(argv)

    docs = args.docs or Path(args.rfq).parent / "docs"
    try:
        report = run_gate(load_rfq(args.rfq), load_store(docs), args.as_of,
                          approvals=args.approve, reviewer=args.reviewer).to_dict()
    except ValueError as e:
        parser.error(str(e))

    print(format_table(report))
    print()
    print(json.dumps(report, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n")
    return EXIT_CODES[report["status"]]
