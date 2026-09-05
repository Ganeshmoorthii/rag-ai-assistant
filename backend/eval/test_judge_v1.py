"""Run Judge V1 against 25 blind hand-labeled ground truth cases."""

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
JUDGE_V1_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "judge_v1.txt")


async def evaluate_v1():
    with open(JUDGE_V1_PATH, "r", encoding="utf-8") as f:
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
        for c in cases:
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
            # Retry loop with backoff
            content = ""
            for attempt in range(4):
                try:
                    resp = await client.post(settings.llm_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        print(f"Rate limited on {cid}, waiting 3s...")
                        await asyncio.sleep(3.0)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        break
                    else:
                        print(f"No choices for {cid}: {data}")
                        await asyncio.sleep(1.0)
                except Exception as e:
                    print(f"Attempt {attempt+1} failed for {cid}: {e}")
                    await asyncio.sleep(1.5)

            if not content:
                print(f"Failed to get response for {cid}, defaulting to verdict FAIL")
                content = json.dumps({"reasoning": "API failure", "verdict": "FAIL"})

            # Parse JSON or fallback
            verdict = 0
            m = re.search(r'"verdict"\s*:\s*"(PASS|FAIL)"', content, re.IGNORECASE)
            if m:
                verdict = 1 if m.group(1).upper() == "PASS" else 0
            else:
                if "PASS" in content and "FAIL" not in content:
                    verdict = 1
            await asyncio.sleep(0.5)

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

    matches = sum(1 for r in results if r["match"])
    agreement = (matches / len(results)) * 100

    print("=" * 60)
    print("JUDGE V1 BASELINE EVALUATION RESULTS")
    print("=" * 60)
    print(f"Agreement Before: {matches}/{len(results)} ({agreement:.1f}%)\n")
    print(f"Total Disagreements: {len(disagreements)}")
    for d in disagreements:
        print(f"\n[{d['case_id']}] Mode: {d['mode']}")
        print(f"  Question: {d['question']}")
        print(f"  Answer: {d['answer']}")
        print(f"  Human Label: {d['human']} | Judge v1 Verdict: {d['judge']}")
        print(f"  Judge Response: {d['raw'].strip()}")

    with open("backend/eval/v1_run_output.json", "w", encoding="utf-8") as f:
        json.dump({"agreement_before": agreement, "results": results, "disagreements": disagreements}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(evaluate_v1())
