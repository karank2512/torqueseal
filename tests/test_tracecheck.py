from datetime import date
from pathlib import Path

import pytest

from tracecheck.cli import main
from tracecheck.engine import BLOCK, HOLD, PASS, RfqLine, evaluate_line, load_rfq, load_store, run_gate

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"
AS_OF = date(2026, 10, 21)


def line(certs=("COC",), pn="NAS6204-12", spec="NAS6204"):
    return RfqLine("T1", pn, "test part", 10, spec, list(certs))


def doc(doc_id="COC-T", doc_type="COC", pn="NAS6204-12", spec="NAS6204", lot="LOT-1",
        heat="H-1", valid_until="2027-06-01"):
    return {"doc_id": doc_id, "doc_type": doc_type, "issuer": "Test Supplier", "part_number": pn,
            "spec": spec, "lot": lot, "heat": heat, "issued": "2026-01-01",
            "valid_until": valid_until, "source_file": f"inbox/{doc_id}.pdf"}


def check(result, name):
    return next(c for c in result.checks if c.name == name)


# PASS path

def test_clean_coc_passes_with_receipt():
    r = evaluate_line(line(), [doc()], AS_OF)
    assert r.decision == PASS
    assert [d["doc_id"] for d in r.documents] == ["COC-T"]
    names = {c.name for c in r.checks}
    assert {"part_number_match", "spec_match", "expiry", "lot_traceability"} <= names


def test_mill_cert_and_coc_with_matching_heat_pass():
    store = [doc("MILL-T", "MILL_CERT", lot=None, heat="H-9"), doc(heat="H-9")]
    r = evaluate_line(line(certs=("MILL_CERT", "COC")), store, AS_OF)
    assert r.decision == PASS
    assert check(r, "lot_continuity").status == PASS


# HOLD path

def test_cert_expiring_within_30_days_holds():
    r = evaluate_line(line(), [doc(valid_until="2026-11-10")], AS_OF)
    assert r.decision == HOLD
    assert "expires 2026-11-10" in r.reason


def test_part_number_formatting_difference_holds():
    r = evaluate_line(line(pn="M83248/1-110", spec="SAE AS83248"),
                      [doc(pn="M83248-1-110", spec="SAE AS83248")], AS_OF)
    assert r.decision == HOLD
    assert check(r, "part_number_match").status == HOLD


def test_exact_doc_preferred_over_partial_match():
    store = [doc("COC-PARTIAL", pn="NAS6204/12"), doc("COC-EXACT")]
    r = evaluate_line(line(), store, AS_OF)
    assert r.decision == PASS
    assert r.documents[0]["doc_id"] == "COC-EXACT"


# BLOCK path

def test_expired_cert_blocks():
    r = evaluate_line(line(), [doc(valid_until="2026-08-01")], AS_OF)
    assert r.decision == BLOCK
    assert "expired" in r.reason


def test_no_document_blocks():
    r = evaluate_line(line(), [], AS_OF)
    assert r.decision == BLOCK
    assert check(r, "document_present").status == BLOCK


def test_mismatched_part_number_blocks_and_is_shown_as_rejected():
    r = evaluate_line(line(pn="NAS1149F0363P", spec="NAS1149"),
                      [doc("COC-WRONG", pn="NAS1149F0332P", spec="NAS1149")], AS_OF)
    assert r.decision == BLOCK
    assert r.documents == []
    assert r.rejected_candidates[0]["doc_id"] == "COC-WRONG"


def test_spec_mismatch_blocks():
    r = evaluate_line(line(), [doc(spec="NAS6203")], AS_OF)
    assert r.decision == BLOCK
    assert check(r, "spec_match").status == BLOCK


def test_coc_missing_lot_blocks():
    r = evaluate_line(line(), [doc(lot=None)], AS_OF)
    assert r.decision == BLOCK
    assert "no lot" in r.reason


def test_heat_mismatch_between_mill_cert_and_coc_blocks():
    store = [doc("MILL-T", "MILL_CERT", lot=None, heat="H-22871"), doc(heat="H-22817")]
    r = evaluate_line(line(certs=("MILL_CERT", "COC")), store, AS_OF)
    assert r.decision == BLOCK
    assert check(r, "lot_continuity").status == BLOCK


def test_block_outranks_hold():
    r = evaluate_line(line(), [doc(pn="NAS6204/12", lot=None)], AS_OF)
    assert r.decision == BLOCK


# Quote gate

def test_all_pass_releases_quote():
    report = run_gate([line()], [doc()], AS_OF)
    assert report.status == "RELEASED" and report.released


def test_single_block_stops_release():
    lines = [line(), RfqLine("T2", "MS27039-1-08", "screw", 5, "NASM27039", ["COC"])]
    store = [doc(), doc("COC-OLD", pn="MS27039-1-08", spec="NASM27039", valid_until="2026-01-01")]
    report = run_gate(lines, store, AS_OF)
    assert report.status == "BLOCKED"
    assert report.released is False


def test_hold_waits_for_review_then_approval_releases():
    store = [doc(valid_until="2026-11-01")]
    assert run_gate([line()], store, AS_OF).status == "AWAITING_REVIEW"
    report = run_gate([line()], store, AS_OF, approvals=["T1"], reviewer="karan")
    assert report.status == "RELEASED"
    assert report.lines[0]["override"]["reviewer"] == "karan"


def test_block_cannot_be_approved():
    with pytest.raises(ValueError, match="only HOLD"):
        run_gate([line()], [doc(valid_until="2026-01-01")], AS_OF, approvals=["T1"])


# Sample data end to end

def test_sample_rfq_decisions():
    report = run_gate(load_rfq(SAMPLE / "rfq.csv"), load_store(SAMPLE / "docs"), AS_OF)
    decisions = {l["line_id"]: l["decision"] for l in report.lines}
    assert decisions == {"L01": PASS, "L02": PASS, "L03": HOLD, "L04": HOLD, "L05": BLOCK,
                         "L06": BLOCK, "L07": BLOCK, "L08": BLOCK, "L09": BLOCK}
    assert report.status == "BLOCKED"


def test_cli_exit_code_and_json(tmp_path, capsys):
    out = tmp_path / "report.json"
    code = main(["run", str(SAMPLE / "rfq.csv"), "--as-of", "2026-10-21", "--json-out", str(out)])
    assert code == 2
    assert "QUOTE NOT RELEASED" in capsys.readouterr().out
    assert '"status": "BLOCKED"' in out.read_text()
