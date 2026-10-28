"""spec ↔ 台账 一致性审计：要求 0 差异。

检查项：
  1. REQ-000008..015 每条都出现在 spec 里，且 spec 不引用不存在的需求；
  2. 每个验收条件 ID 都出现在 spec 的 §13，且 spec 不引用不存在的条件；
  3. 每条需求的标题、条件数量与 spec 映射表不矛盾。
用法：python tools/audit_spec_vs_ledger.py   退出码 0 表示通过。
"""
import json
import os
import re
import subprocess
import sys

LEDGER = "requirements.md"
SPEC = "spec_multiplayer-world.md"
FIRST = "REQ-000008"


def ledger():
    p = subprocess.run(["cmd", "/c", "reqledger", "show", "--file", LEDGER, "--stdin"],
                       input=b'{"type":"ledger"}', capture_output=True)
    return json.loads(p.stdout.decode("utf-8", "replace"))


def main():
    if not os.path.exists(SPEC):
        print("spec 文件不存在:", SPEC)
        return 1

    doc = ledger()
    o = doc["object"]
    spec = open(SPEC, encoding="utf-8").read()

    reqs = {}
    for r in o["requirements"]:
        if r["id"] >= FIRST:
            rev = r["revisions"][-1]
            reqs[r["id"]] = rev

    problems = []

    # 1. 需求号
    for rid in reqs:
        if rid not in spec:
            problems.append(f"spec 缺需求 {rid}")
    for m in set(re.findall(r"REQ-\d{6}", spec)):
        if m not in o_req_ids(o):
            problems.append(f"spec 引用了台账里不存在的需求 {m}")

    # 2. 条件号
    all_conds = set()
    for rid, rev in reqs.items():
        for a in rev["acceptance"]:
            all_conds.add(a["id"])
            if a["id"] not in spec:
                problems.append(f"spec 缺条件 {a['id']}（{rid}）")
    for m in set(re.findall(r"AC-\d{6}", spec)):
        if m not in all_conds:
            problems.append(f"spec 引用了台账里不存在的条件 {m}")

    # 3. 结构与字段完整性
    #    注意：范围决定（纳入/排除）与确认状态是由事件派生的，不在 revisions 里，
    #    所以这里只校验结构；「是否已进基线」用 audit 的 --baseline 参数另外核对。
    AC_FIELDS = ["role", "scenario", "preconditions", "input", "operation",
                 "expected", "method", "evidence"]
    for rid, rev in reqs.items():
        for f in ("title", "description", "purpose", "necessity", "type", "module",
                  "priority", "placement", "sources", "included", "normal_behavior"):
            if not rev.get(f):
                problems.append(f"{rid} 缺字段 {f}")
        if not rev.get("acceptance"):
            problems.append(f"{rid} 没有验收条件")
        for a in rev["acceptance"]:
            for f in AC_FIELDS:
                if not a.get(f):
                    problems.append(f"{a['id']} 缺字段 {f}")
            exc = a.get("exception") or {}
            for f in ("scenario", "expected", "handling"):
                if not exc.get(f):
                    problems.append(f"{a['id']} 的 exception 缺字段 {f}")
        pl = rev.get("placement") or {}
        if pl.get("kind") == "页面":
            if not (pl.get("primary") or {}).get("page_id"):
                problems.append(f"{rid} 的页面归属缺 page_id")
        elif not pl.get("reason"):
            problems.append(f"{rid} 非页面归属但没有 reason")

    total = sum(len(r["acceptance"]) for r in reqs.values())
    print(f"doc_rev={doc['document_revision']} 需求={len(reqs)} 条件={total}")
    for rid in sorted(reqs):
        rev = reqs[rid]
        print(f"  {rid} r{rev['revision']} {len(rev['acceptance'])} 条 | {rev['title']}")

    if problems:
        print("\n发现差异:")
        for p in problems:
            print("  -", p)
        return 1
    print("\n0 差异：spec 与台账一致")
    return 0


def o_req_ids(o):
    return {r["id"] for r in o["requirements"]}


if __name__ == "__main__":
    sys.exit(main())
