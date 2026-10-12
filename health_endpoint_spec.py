#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""health-endpoint-spec — liveness/readiness semantics spec + response validator.

Validates a health endpoint specification (which endpoints exist, their
liveness-vs-readiness semantics, declared status codes and body schema) and
checks recorded sample responses against the spec. Pure stdlib.
"""
import argparse
import json
import sys

KINDS = ("liveness", "readiness")
BODY_STATUS_CODES = {"ok": 200, "degraded": 503, "down": 503}
DEP_KEYS = ("database", "db", "redis", "cache", "queue", "broker",
            "dependencies", "deps", "upstream", "storage")


class SpecError(Exception):
    """Recoverable input error surfaced as exit 2."""


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def validate_spec(spec):
    """Validate a spec: {"endpoints": [{path, kind, status_code, body}]}."""
    findings = []
    if not isinstance(spec, dict) or not isinstance(spec.get("endpoints"), list):
        raise SpecError("spec must be {\"endpoints\": [...]}")
    paths = {}
    for i, ep in enumerate(spec["endpoints"]):
        if not isinstance(ep, dict):
            findings.append(("fail", "E000", i, None, "endpoint entry %d is not an object" % i))
            continue
        path = ep.get("path")
        kind = ep.get("kind")
        code = ep.get("status_code")
        body = ep.get("body")
        if not isinstance(path, str) or not path.startswith("/"):
            findings.append(("fail", "E009", i, path, "path must be a string starting with '/'"))
            path = "<bad:%d>" % i
        if path in paths:
            findings.append(("fail", "E006", i, path, "duplicate endpoint path %r" % path))
        paths[path] = True
        if kind not in KINDS:
            findings.append(("fail", "E001", i, path,
                             "unknown kind %r (expected liveness|readiness)" % (kind,)))
            continue
        # convention: liveness under /healthz*, readiness under /readyz*
        low = path.lower()
        if kind == "liveness" and not low.startswith("/healthz") and "live" not in low:
            findings.append(("warn", "E007", i, path,
                             "liveness endpoint not under /healthz* or *live*"))
        if kind == "readiness" and not low.startswith("/readyz") and "ready" not in low:
            findings.append(("warn", "E007", i, path,
                             "readiness endpoint not under /readyz* or *ready*"))
        if kind == "liveness":
            dep_hits = [k for k in DEP_KEYS if isinstance(body, dict) and k in body]
            if dep_hits:
                findings.append(("fail", "E002", i, path,
                                 "liveness body references dependencies %s; liveness must be self-contained"
                                 % ", ".join(dep_hits)))
        if kind == "readiness" and not (isinstance(body, dict) and "checks" in body):
            findings.append(("warn", "E003", i, path,
                             "readiness body lacks a 'checks' map"))
        if not _is_int(code) or code not in (200, 503):
            findings.append(("fail", "E004", i, path,
                             "status_code must be 200 or 503, got %r" % (code,)))
            continue
        if not isinstance(body, dict):
            findings.append(("fail", "E008", i, path, "body must be an object"))
            continue
        status_val = body.get("status")
        if status_val not in BODY_STATUS_CODES:
            findings.append(("fail", "E005", i, path,
                             "body.status must be one of %s, got %r"
                             % ("/".join(BODY_STATUS_CODES), status_val)))
        else:
            implied = BODY_STATUS_CODES[status_val]
            if implied != code:
                findings.append(("fail", "E005", i, path,
                                 "body.status=%r implies %d but status_code is %d"
                                 % (status_val, implied, code)))
    return findings


def probe_samples(spec, samples):
    """Check recorded samples [{path, code, body}] against the spec."""
    results = []
    index = {}
    for ep in spec.get("endpoints", []):
        if isinstance(ep, dict) and isinstance(ep.get("path"), str):
            index[ep["path"]] = ep
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            results.append({"index": i, "ok": False, "problems": ["sample is not an object"]})
            continue
        path = sample.get("path")
        code = sample.get("code")
        body = sample.get("body")
        problems = []
        ep = index.get(path)
        if ep is None:
            problems.append("path %r not declared in spec" % (path,))
        else:
            if _is_int(code) and _is_int(ep.get("status_code")) and code != ep["status_code"]:
                problems.append("code %s != declared %s" % (code, ep["status_code"]))
            if isinstance(body, dict):
                sv = body.get("status")
                if sv in BODY_STATUS_CODES and _is_int(code) and BODY_STATUS_CODES[sv] != code:
                    problems.append("body.status=%r inconsistent with code %s" % (sv, code))
                if ep.get("kind") == "liveness":
                    hits = [k for k in DEP_KEYS if k in body]
                    if hits:
                        problems.append("liveness response exposes deps: %s" % ", ".join(hits))
            else:
                problems.append("body must be an object")
        results.append({"index": i, "path": path, "ok": not problems, "problems": problems})
    return results


def _cmd_validate(args):
    spec = load_json(args.spec)
    findings = validate_spec(spec)
    sev = {"fail": "FAIL", "warn": "WARN"}
    payload = {"findings": [dict(severity=sev[f[0]], code=f[1], index=f[2], path=f[3], message=f[4])
                            for f in findings]}
    payload["summary"] = {
        "fails": sum(1 for f in payload["findings"] if f["severity"] == "FAIL"),
        "warns": sum(1 for f in payload["findings"] if f["severity"] == "WARN"),
        "endpoints": len(spec.get("endpoints", [])) if isinstance(spec, dict) else 0,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for f in payload["findings"]:
            print("%s %s ep=%s: %s" % (f["severity"], f["code"], f["path"], f["message"]))
        print("summary: %d fail(s), %d warn(s), %d endpoint(s)"
              % (payload["summary"]["fails"], payload["summary"]["warns"],
                 payload["summary"]["endpoints"]))
    return 1 if payload["summary"]["fails"] else 0


def _cmd_probe(args):
    spec = load_json(args.spec)
    with open(args.samples, "r", encoding="utf-8", newline="") as fh:
        samples = [json.loads(line) for line in fh if line.strip()]
    results = probe_samples(spec, samples)
    bad = [r for r in results if not r["ok"]]
    payload = {"results": results, "summary": {"samples": len(results), "failures": len(bad)}}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r["ok"]:
                print("sample %s %s: OK" % (r["index"], r.get("path")))
            else:
                for p in r["problems"]:
                    print("sample %s %s: FAIL %s" % (r["index"], r.get("path"), p))
        print("summary: %d/%d samples conform" % (len(results) - len(bad), len(results)))
    return 1 if bad else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="health-endpoint-spec",
        description="Validate health endpoint specs (liveness/readiness separation, "
                    "status/body schema) and probe recorded samples against them.")
    sub = parser.add_subparsers(dest="cmd")
    p_v = sub.add_parser("validate", help="validate a spec JSON")
    p_v.add_argument("spec")
    p_v.add_argument("--json", action="store_true")
    p_p = sub.add_parser("probe", help="check recorded samples against a spec")
    p_p.add_argument("--spec", required=True)
    p_p.add_argument("--samples", required=True, help="JSONL of {path, code, body}")
    p_p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd not in ("validate", "probe"):
        parser.print_help()
        return 2
    try:
        return _cmd_validate(args) if args.cmd == "validate" else _cmd_probe(args)
    except (SpecError, OSError, json.JSONDecodeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
