# -*- coding: utf-8 -*-
"""self_test for health-endpoint-spec — inherits scaffold-v2 defenses D1-D4."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")  # D3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_endpoint_spec as mod  # noqa: E402


def run_cli(argv):  # D1
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            rc = mod.main(argv)
            code = 0 if rc is None else rc
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:  # noqa: BLE001
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


CASES = []


def case(name, cat):
    def deco(fn):
        CASES.append((name, cat, fn))
        return fn
    return deco


TMP = tempfile.mkdtemp(prefix="hes_selftest_")


def write_file(name, obj):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8", newline="") as fh:  # D3
        if isinstance(obj, str):
            fh.write(obj)
        else:
            json.dump(obj, fh, ensure_ascii=False)
    return p


def ep(path, kind, code=200, body=None):
    if body is None:
        body = {"status": "ok"}
    return {"path": path, "kind": kind, "status_code": code, "body": body}


def codes(fs):
    return [f[1] for f in fs]


GOOD_SPEC = {"endpoints": [
    ep("/healthz", "liveness"),
    ep("/readyz", "readiness", 200, {"status": "ok", "checks": {"db": "ok"}}),
]}

# ------------------------------------------------------------------ [A] functional

@case("A01_valid_spec_clean", "A")
def t():
    assert mod.validate_spec(GOOD_SPEC) == []

@case("A02_liveness_convention_ok", "A")
def t():
    assert mod.validate_spec({"endpoints": [ep("/healthz", "liveness")]}) == []

@case("A03_readiness_convention_ok", "A")
def t():
    assert mod.validate_spec({"endpoints": [ep("/readyz", "readiness", 200,
                                                   {"status": "ok", "checks": {}})]}) == []

@case("A04_unknown_kind_E001", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/x", "deep")]} )
    assert "E001" in codes(f)

@case("A05_liveness_with_deps_E002", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200,
                                                  {"status": "ok", "database": "up"})]})
    assert "E002" in codes(f)

@case("A06_readiness_no_checks_E003", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/readyz", "readiness")]})
    assert "E003" in codes(f)

@case("A07_bad_status_code_E004", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 500)]})
    assert "E004" in codes(f)

@case("A08_status_body_mismatch_E005", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200, {"status": "down"})]})
    assert "E005" in codes(f)

@case("A09_duplicate_path_E006", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness"), ep("/healthz", "liveness")]})
    assert "E006" in codes(f)

@case("A10_liveness_wrong_path_E007", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/status", "liveness")]})
    assert codes(f) == ["E007"]

@case("A11_missing_body_status_E005", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200, {"note": "hi"})]})
    assert "E005" in codes(f)

@case("A12_body_not_object_E008", "A")
def t():
    f = mod.validate_spec({"endpoints": [dict(path="/healthz", kind="liveness",
                                              status_code=200, body="ok")]})
    assert "E008" in codes(f)

@case("A13_path_not_slash_E009", "A")
def t():
    f = mod.validate_spec({"endpoints": [dict(path="healthz", kind="liveness",
                                              status_code=200, body={"status": "ok"})]})
    assert "E009" in codes(f)

@case("A14_degraded_maps_503", "A")
def t():
    assert mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 503, {"status": "degraded"})]}) == []

@case("A15_down_maps_503", "A")
def t():
    assert mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 503, {"status": "down"})]}) == []

@case("A16_live_substring_convention", "A")
def t():
    assert mod.validate_spec({"endpoints": [ep("/live", "liveness")]}) == []

@case("A17_ready_substring_convention", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/ready", "readiness", 200,
                                                  {"status": "ok", "checks": {}})]})
    assert "E007" not in codes(f)

@case("A18_probe_matching_sample_ok", "A")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/healthz", "code": 200, "body": {"status": "ok"}}])
    assert r[0]["ok"] is True

@case("A19_probe_undeclared_path", "A")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/nope", "code": 200, "body": {"status": "ok"}}])
    assert r[0]["ok"] is False and "not declared" in r[0]["problems"][0]

@case("A20_probe_code_mismatch", "A")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/healthz", "code": 503, "body": {"status": "down"}}])
    assert r[0]["ok"] is False

@case("A21_probe_liveness_dep_leak", "A")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/healthz", "code": 200,
                                       "body": {"status": "ok", "redis": "up"}}])
    assert r[0]["ok"] is False and any("redis" in p for p in r[0]["problems"])

@case("A22_probe_body_status_vs_code", "A")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/healthz", "code": 200, "body": {"status": "degraded"}}])
    assert r[0]["ok"] is False

@case("A23_cli_validate_clean", "A")
def t():
    p = write_file("good.json", GOOD_SPEC)
    code, out, _ = run_cli(["validate", p])
    assert code == 0 and "0 fail" in out

@case("A24_cli_validate_fail", "A")
def t():
    p = write_file("bad.json", {"endpoints": [ep("/healthz", "liveness", 200, {"status": "ok", "db": "x"})]})
    code, out, _ = run_cli(["validate", p])
    assert code == 1 and "E002" in out

@case("A25_cli_probe_clean", "A")
def t():
    sp = write_file("s25.json", GOOD_SPEC)
    mp = write_file("m25.jsonl", '{"path": "/healthz", "code": 200, "body": {"status": "ok"}}\n')
    code, out, _ = run_cli(["probe", "--spec", sp, "--samples", mp])
    assert code == 0 and "1/1 samples conform" in out

# ------------------------------------------------------------------ [B] exception / CLI contract

@case("B01_cli_no_subcommand_exit2", "B")
def t():
    assert run_cli([])[0] == 2

@case("B02_cli_unknown_subcommand_exit2", "B")
def t():
    assert run_cli(["lint", "x"])[0] == 2

@case("B03_validate_missing_file_exit2", "B")
def t():
    code, _, err = run_cli(["validate", os.path.join(TMP, "ghost.json")])
    assert code == 2 and "error" in err

@case("B04_spec_not_object_exit2", "B")
def t():
    p = write_file("b04.json", [1])
    code, _, err = run_cli(["validate", p])
    assert code == 2 and "endpoints" in err

@case("B05_endpoints_not_list_exit2", "B")
def t():
    p = write_file("b05.json", {"endpoints": 3})
    code, _, _ = run_cli(["validate", p])
    assert code == 2

@case("B06_endpoint_entry_not_object", "B")
def t():
    f = mod.validate_spec({"endpoints": ["x"]})
    assert codes(f) == ["E000"]

@case("B07_probe_missing_samples_exit2", "B")
def t():
    sp = write_file("b07.json", GOOD_SPEC)
    assert run_cli(["probe", "--spec", sp, "--samples", "ghost.jsonl"])[0] == 2

@case("B08_probe_missing_spec_exit2", "B")
def t():
    mp = write_file("b08.jsonl", [{"path": "/healthz", "code": 200, "body": {"status": "ok"}}])
    assert run_cli(["probe", "--spec", "ghost.json", "--samples", mp])[0] == 2

@case("B09_probe_bad_jsonl_exit2", "B")
def t():
    sp = write_file("b09.json", GOOD_SPEC)
    mp = os.path.join(TMP, "b09.jsonl")
    with open(mp, "w", encoding="utf-8", newline="") as fh:
        fh.write("{bad json\n")
    assert run_cli(["probe", "--spec", sp, "--samples", mp])[0] == 2

@case("B10_probe_sample_not_object", "B")
def t():
    r = mod.probe_samples(GOOD_SPEC, ["nope"])
    assert r[0]["ok"] is False

@case("B11_probe_body_not_object", "B")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/healthz", "code": 200, "body": "ok"}])
    assert r[0]["ok"] is False and any("object" in p for p in r[0]["problems"])

@case("B12_cli_json_validate_keys", "B")
def t():
    p = write_file("b12.json", {"endpoints": [ep("/healthz", "liveness", 500)]})
    code, out, _ = run_cli(["validate", p, "--json"])
    data = json.loads(out)
    assert code == 1 and data["summary"]["fails"] == 1 and data["findings"][0]["code"] == "E004"

@case("B13_cli_json_probe_summary", "B")
def t():
    sp = write_file("b13.json", GOOD_SPEC)
    mp = write_file("b13m.jsonl", [{"path": "/healthz", "code": 200, "body": {"status": "ok"}},
                                   {"path": "/zzz", "code": 200, "body": {}}])
    code, out, _ = run_cli(["probe", "--spec", sp, "--samples", mp, "--json"])
    data = json.loads(out)
    assert code == 1 and data["summary"]["failures"] == 1

@case("B14_index_in_findings", "B")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness"), ep("/x", "bad")]})
    assert f[0][2] == 1  # second entry

@case("B15_dep_key_alias_db", "A")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200, {"status": "ok", "db": "up"})]})
    assert "E002" in codes(f)

@case("B16_help_text", "B")
def t():
    code, out, _ = run_cli(["--help"])
    assert code == 0 and "health" in out

@case("B17_warn_not_fail_exit0", "B")
def t():
    p = write_file("b17.json", {"endpoints": [ep("/status", "liveness")]})
    code, out, _ = run_cli(["validate", p])
    assert code == 0 and "WARN" in out

@case("B18_probe_extra_fields_tolerated", "B")
def t():
    r = mod.probe_samples(GOOD_SPEC, [{"path": "/healthz", "code": 200,
                                       "body": {"status": "ok", "version": "1.0"}}])
    assert r[0]["ok"] is True

@case("B19_validate_returns_list_not_raise", "B")
def t():
    assert isinstance(mod.validate_spec({"endpoints": []}), list)

@case("B20_severity_labels_in_text_out", "B")
def t():
    p = write_file("b20.json", {"endpoints": [ep("/x", "nope")]})
    code, out, _ = run_cli(["validate", p])
    assert "FAIL" in out

# ------------------------------------------------------------------ [C] extreme edge

@case("C01_empty_endpoints_clean", "C")
def t():
    assert mod.validate_spec({"endpoints": []}) == []

@case("C02_unicode_paths", "C")
def t():
    f = mod.validate_spec({"endpoints": [ep("/健康检查", "liveness")]})
    assert "E007" in codes(f)  # non-conventional path, unicode safe

@case("C03_unicode_check_names_ok", "C")
def t():
    spec = {"endpoints": [ep("/readyz", "readiness", 200,
                                   {"status": "ok", "checks": {"数据库": "ok"}})]}
    assert mod.validate_spec(spec) == []

@case("C04_emoji_body_values", "C")
def t():
    spec = {"endpoints": [ep("/readyz", "readiness", 200,
                                   {"status": "ok", "checks": {"🚀": "✅"}})]}
    assert mod.validate_spec(spec) == []

@case("C05_crlf_samples_jsonl", "C")
def t():
    sp = write_file("c05.json", GOOD_SPEC)
    mp = os.path.join(TMP, "c05.jsonl")
    with open(mp, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(json.dumps({"path": "/healthz", "code": 200, "body": {"status": "ok"}}) + "\r\n")
    code, out, _ = run_cli(["probe", "--spec", sp, "--samples", mp])
    assert code == 0

@case("C06_blank_lines_in_jsonl", "C")
def t():
    sp = write_file("c06.json", GOOD_SPEC)
    mp = os.path.join(TMP, "c06.jsonl")
    with open(mp, "w", encoding="utf-8", newline="") as fh:
        fh.write('\n{"path": "/healthz", "code": 200, "body": {"status": "ok"}}\n\n')
    assert run_cli(["probe", "--spec", sp, "--samples", mp])[0] == 0

@case("C07_large_spec_performance", "C")
def t():
    spec = {"endpoints": [ep("/healthz%d" % i, "liveness") for i in range(5000)]}
    import time
    t0 = __import__("time").perf_counter()
    assert mod.validate_spec(spec) == []
    assert __import__("time").perf_counter() - t0 < 3

@case("C08_many_samples_probe", "C")
def t():
    samples = [{"path": "/healthz", "code": 200, "body": {"status": "ok"}} for _ in range(3000)]
    r = mod.probe_samples(GOOD_SPEC, samples)
    assert all(x["ok"] for x in r)

@case("C09_dep_key_upstream", "C")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200,
                                                  {"status": "ok", "upstream": "x"})]})
    assert "E002" in codes(f)

@case("C10_dep_key_storage", "C")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200,
                                                  {"status": "ok", "storage": "x"})]})
    assert "E002" in codes(f)

@case("C11_status_int_vs_bool", "C")
def t():
    f = mod.validate_spec({"endpoints": [dict(path="/healthz", kind="liveness",
                                              status_code=True, body={"status": "ok"})]})
    assert "E004" in codes(f)

@case("C12_duplicate_path_both_reported", "C")
def t():
    f = mod.validate_spec({"endpoints": [ep("/readyz", "readiness", 200, {"status": "ok", "checks": {}}),
                                         ep("/readyz", "readiness", 200, {"status": "ok", "checks": {}})]})
    assert codes(f) == ["E006"]

@case("C13_503_degraded_ready_ok", "C")
def t():
    spec = {"endpoints": [ep("/readyz", "readiness", 503,
                                    {"status": "degraded", "checks": {"db": "down"}})]}
    assert mod.validate_spec(spec) == []

@case("C14_path_case_insensitive_convention", "C")
def t():
    f = mod.validate_spec({"endpoints": [ep("/HEALTHZ", "liveness")]})
    assert "E007" not in codes(f)

@case("C15_livez_variant", "C")
def t():
    assert mod.validate_spec({"endpoints": [ep("/livez", "liveness")]}) == []

@case("C16_bom_spec_file", "C")
def t():
    p = os.path.join(TMP, "c16.json")
    with open(p, "w", encoding="utf-8-sig", newline="") as fh:
        json.dump(GOOD_SPEC, fh)
    code, _, _ = run_cli(["validate", p])
    assert code in (0, 2)  # tolerated, must not crash

@case("C17_empty_body_fails", "C")
def t():
    f = mod.validate_spec({"endpoints": [ep("/healthz", "liveness", 200, {})]})
    assert "E005" in codes(f)

@case("C18_checks_non_dict_value_ok", "C")
def t():
    spec = {"endpoints": [ep("/readyz", "readiness", 200,
                                    {"status": "ok", "checks": []})]}
    assert mod.validate_spec(spec) == []  # presence is what matters

@case("C19_mixed_spec_multi_findings", "C")
def t():
    spec = {"endpoints": [ep("/healthz", "liveness", 200, {"status": "ok", "queue": "up"}),
                          ep("/readyz", "readiness"),
                          ep("/weird", "liveness", 418)]}
    f = mod.validate_spec(spec)
    assert {"E002", "E003", "E004"} <= set(codes(f))

@case("C20_json_output_ensure_ascii_false", "C")
def t():
    spec = {"endpoints": [ep("/健康检查", "liveness")]}
    p = write_file("c20.json", spec)
    code, out, _ = run_cli(["validate", p, "--json"])
    assert "健康检查" in out

class TestAll(unittest.TestCase):
    pass


def _build():
    for i, (name, cat, fn) in enumerate(CASES):
        def make(f):
            def m(self):
                f()
            return m
        slug = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
        setattr(TestAll, "test_%s_%03d_%s" % (cat, i, slug), make(fn))
_build()


class TestMeta(unittest.TestCase):
    def test_case_count_ge_60(self):
        self.assertGreaterEqual(len(CASES), 60)

    def test_categories_present(self):
        self.assertEqual({c for _, c, _ in CASES}, {"A", "B", "C"})


if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))  # D4
    sys.exit(0 if fails == 0 else 1)
