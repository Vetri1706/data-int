"""Offline labelled claim benchmark. No model calls or network retrieval.

Synthetic author-labelled cases; NOT independently adjudicated web accuracy.
Both verifiers receive identical candidate values and source text. Report
abstention/recall as well as false support so a reject-all verifier cannot win.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "services/intelligence"))
from claims import verify_claim
from baseline_support import supported


def run():
    fixture=json.loads((ROOT / "evaluation/fixtures/claim_adversarial.json").read_text(encoding="utf-8"))
    rows=[]
    for case in fixture["cases"]:
        chunk={"text":case["text"],"http_status":200,"url":"https://benchmark.example/source","chunk_id":case["id"],"char_start":0,"content_sha256":hashlib.sha256(case["text"].encode()).hexdigest()}
        start=time.perf_counter()
        old="supported" if supported(case["value"],case["text"]) else "unknown"
        old_ms=(time.perf_counter()-start)*1000
        start=time.perf_counter()
        new=verify_claim(case["entity"],case["field"],case["value"],chunk)["state"]
        rows.append({"id":case["id"],"split":case["split"],"expected":case["expected"],"baseline":old,"typed":new,"baseline_ms":old_ms,"typed_ms":(time.perf_counter()-start)*1000})
    def metrics(data, verifier):
        tp=sum(r[verifier]=="supported" and r["expected"]=="supported" for r in data)
        fp=sum(r[verifier]=="supported" and r["expected"]!="supported" for r in data)
        positives=sum(r["expected"]=="supported" for r in data)
        return {"cases":len(data),"true_support":tp,"false_support":fp,"support_precision":tp/(tp+fp) if tp+fp else None,
                "support_recall":tp/positives if positives else None,"three_state_accuracy":sum(r[verifier]==r["expected"] for r in data)/len(data),
                "abstentions":sum(r[verifier]=="unknown" for r in data),"total_ms":round(sum(r[verifier+"_ms"] for r in data),3)}
    report={"scope":fixture["scope"],"baseline_commit":"2981853", "metrics":{split:{v:metrics([r for r in rows if split=="all" or r["split"]==split],v) for v in ["baseline","typed"]} for split in ["all","regression","challenge"]},"cases":rows}
    path=ROOT / "evaluation/results/claim_benchmark.json"
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report["metrics"],indent=2))


if __name__=="__main__":
    run()
