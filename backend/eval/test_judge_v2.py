"""Run Judge V2 against 25 blind hand-labeled ground truth cases with robust rate-limit handling."""

import asyncio
import json
import os
import re
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core.config import settings
import httpx

EVAL_SET_PATH = os.path.join(os.path.dirname(__file__), "eval_set_25.json")
LABELS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "labels_25.json")
JUDGE_V2_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "judge_v2.txt")


async def evaluate_v2():
    with open(JUDGE_V2_PATH, "r", encoding="utf-8") as f:
        prompt_tmpl = f.read()
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)["labels"]

    results = []
    disagreements = []
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        for idx, c in enumerate(cases):
            cid = c["case_id"]
            prompt = (
                prompt_tmpl
                .replace("{question}", c["question"])
                .replace("{context}", c["context"])
                .replace("{answer}", c["answer"])
            )
            payload = {
                "model": settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            }

            content = ""
            for attempt in range(6):
                try:
                    resp = await client.post(settings.llm_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        wait_sec = 6.0 + attempt * 3.0
                        print(f"[{cid}] Rate limited (429), waiting {wait_sec}s...")
                        await asyncio.sleep(wait_sec)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        break
                    else:
                        print(f"[{cid}] No choices returned: {data}")
                        await asyncio.sleep(2.0)
                except Exception as e:
                    print(f"[{cid}] Attempt {attempt+1} error: {e}")
                    await asyncio.sleep(3.0)

            if not content:
                print(f"[{cid}] FAILED after all retries.")
                content = json.dumps({"reasoning": "Failed to get API response", "verdict": "FAIL"})

            # Parse JSON verdict
            verdict = 0
            m = re.search(r'"verdict"\s*:\s*"(PASS|FAIL)"', content, re.IGNORECASE)
            if m:
                verdict = 1 if m.group(1).upper() == "PASS" else 0
            else:
                if "PASS" in content and "FAIL" not in content:
                    verdict = 1

            human_label = ground_truth[cid]["human_label"]
            match = (verdict == human_label)
            results.append({
                "case_id": cid,
                "mode": c["mode"],
                "question": c["question"],
                "answer": c["answer"],
                "verdict": verdict,
                "human": human_label,
                "match": match,
                "content": content
            })
            if not match:
                disagreements.append({
                    "case_id": cid,
                    "mode": c["mode"],
                    "question": c["question"],
                    "answer": c["answer"],
                    "human": human_label,
                    "judge": verdict,
                    "raw": content
                })

            print(f"[{cid}] Evaluated: Judge={verdict}, Human={human_label}, Match={match}")
            await asyncio.sleep(1.0)

    matches = sum(1 for r in results if r["match"])
    agreement = (matches / len(results)) * 100

    print("\n" + "=" * 60)
    print("JUDGE V2 ITERATED EVALUATION RESULTS")
    print("=" * 60)
    print(f"Agreement After: {matches}/{len(results)} ({agreement:.1f}%)\n")
    print(f"Total Disagreements: {len(disagreements)}")
    for d in disagreements:
        print(f"\n[{d['case_id']}] Mode: {d['mode']}")
        print(f"  Question: {d['question']}")
        print(f"  Human Label: {d['human']} | Judge v2 Verdict: {d['judge']}")
        print(f"  Judge Response: {d['raw'].strip()}")

    with open("backend/eval/v2_run_output.json", "w", encoding="utf-8") as f:
        json.dump({"agreement_after": agreement, "results": results, "disagreements": disagreements}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(evaluate_v2())
