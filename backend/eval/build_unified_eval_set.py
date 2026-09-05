import json
import os

GT_PATH = os.path.join(os.path.dirname(__file__), "..", "eval_ground_truth_results.json")
TRACES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "traces.jsonl")
OUTPUT_SET = os.path.join(os.path.dirname(__file__), "eval_set_25.json")
OUTPUT_LABELS = os.path.join(os.path.dirname(__file__), "..", "..", "labels_25.json")

# Load the 20 Q&A results
with open(GT_PATH, "r", encoding="utf-8") as f:
    gt_20 = json.load(f)

# Load traces
traces = {}
with open(TRACES_PATH, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            t = json.loads(line.strip())
            traces[t.get("trace_id")] = t

# Mode mapping for Q1-Q20 based on Week 5 error taxonomy
mode_map = {
    "Q1": "partial_multihop_context_truncation",
    "Q2": "partial_multihop_context_truncation",
    "Q3": "partial_multihop_context_truncation",
    "Q4": "partial_multihop_context_truncation",
    "Q5": "wildcard_and_special_char_token_dropped",
    "Q6": "partial_multihop_context_truncation",
    "Q7": "partial_multihop_context_truncation",
    "Q8": "omitted_prerequisite_header_or_import",
    "Q9": "numeric_status_code_confusion",
    "Q10": "omitted_prerequisite_header_or_import",
    "Q11": "partial_multihop_context_truncation",
    "Q12": "wildcard_and_special_char_token_dropped",
    "Q13": "partial_multihop_context_truncation",
    "Q14": "partial_multihop_context_truncation",
    "Q15": "wildcard_and_special_char_token_dropped",
    "Q16": "omitted_prerequisite_header_or_import",
    "Q17": "wildcard_and_special_char_token_dropped",
    "Q18": "omitted_prerequisite_header_or_import",
    "Q19": "omitted_prerequisite_header_or_import",
    "Q20": "omitted_prerequisite_header_or_import"
}

unified_cases = []
labels = {}

for item in gt_20:
    qid = item["id"]
    mode = mode_map[qid]
    
    # Ground truth human label: 1 if passed_all or pass_rate >= 0.8, else 0
    passed = item.get("passed_all", False)
    human_label = 1 if passed else 0
    
    context_str = "\n".join([f"[{c}]" for c in item.get("chunks", [])])
    
    case_obj = {
        "case_id": qid,
        "trace_id": None,
        "is_regression": False,
        "mode": mode,
        "question": item["question"],
        "required_version": None,
        "context": context_str,
        "answer": item["answer"],
        "must_contain": item.get("must_contain", []),
        "pass_rate": item.get("pass_rate", 0.0),
        "ground_truth": f"Must contain: {', '.join(item.get('must_contain', []))}"
    }
    unified_cases.append(case_obj)
    labels[qid] = {
        "human_label": human_label,
        "reason": f"Gold set criteria met: {passed} (pass_rate: {item.get('pass_rate', 0.0)})"
    }

# Add the 5 regression traces from Week 5
regression_specs = [
    {
        "case_id": "Q21",
        "trace_id": "tr_042",
        "is_regression": True,
        "mode": "v2_signature_returned_for_v3_query",
        "question": "How do I call `getBackorders()` in SDK v3?",
        "required_version": "v3",
        "context": "[Advita FE.pdf p.3]\ngetBackorders(agencyId)\nFetches backorder records for the specified agency.",
        "answer": "`getBackorders` accepts single agencyId parameter: getBackorders(agencyId) [Advita FE.pdf p.3].",
        "ground_truth": "In SDK v3, getBackorders requires an options object: getBackorders({ agencyId, includeDrafts }). Recommending positional parameter is legacy v2.",
        "human_label": 0,
        "reason": "Recommends deprecated v2 getBackorders(agencyId) signature for an SDK v3 query."
    },
    {
        "case_id": "Q22",
        "trace_id": "tr_050",
        "is_regression": True,
        "mode": "omitted_prerequisite_header_or_import",
        "question": "How do I make an HTTP request to /api/v1/impersonate?",
        "required_version": None,
        "context": "[Cim Authentication.pdf p.3]\nPOST /api/v1/impersonate body: { 'userId': '123' }",
        "answer": "Send POST to /api/v1/impersonate with target userId: {'userId': 'target_user_id'} [Cim Authentication.pdf p.3].",
        "ground_truth": "POST to /api/v1/impersonate with JSON body. Must include prerequisite Authorization: Bearer <admin_token> header.",
        "human_label": 0,
        "reason": "Omits mandatory prerequisite Authorization Bearer token header, causing 401 Unauthorized."
    },
    {
        "case_id": "Q23",
        "trace_id": "tr_048",
        "is_regression": True,
        "mode": "wildcard_and_special_char_token_dropped",
        "question": "What does wildcard * mean in permission strings?",
        "required_version": None,
        "context": "[Cim Authentication.pdf p.7]\nPermission format: service:resource:action. Wildcard * matches all resources or actions.",
        "answer": "Permission strings format is service:resource:action where wildcard * matches all resources or actions [Cim Authentication.pdf p.7].",
        "ground_truth": "Wildcard * matches any action or resource within the permission namespace.",
        "human_label": 1,
        "reason": "Correctly explains wildcard * syntax and semantics in permission strings."
    },
    {
        "case_id": "Q24",
        "trace_id": "tr_067",
        "is_regression": True,
        "mode": "numeric_status_code_confusion",
        "question": "When does the auth server return 403 versus 401?",
        "required_version": None,
        "context": "[Cim Authentication.pdf p.8]\nHTTP 401 is returned when token is missing/expired. HTTP 403 is returned when user has insufficient permissions.",
        "answer": "HTTP 401 is returned when authentication token is missing or expired. HTTP 403 is returned when user lacks permission [Cim Authentication.pdf p.8].",
        "ground_truth": "401 = unauthenticated; 403 = authenticated but unauthorized.",
        "human_label": 1,
        "reason": "Accurately distinguishes 401 Unauthorized from 403 Forbidden."
    },
    {
        "case_id": "Q25",
        "trace_id": "tr_001",
        "is_regression": True,
        "mode": "v2_signature_returned_for_v3_query",
        "question": "How do I initialize the Cimplicity AuthClient in v3 SDK?",
        "required_version": "v3",
        "context": "[Cim Authentication v3.pdf p.5]\nAuthClient initialization (v3.0+):\nconst client = new AuthClient({ tokenProvider: myProvider, tenantId: 't-99' });\nAPI Key options removed.",
        "answer": "To initialize AuthClient in SDK v3, use `const client = new AuthClient({ tokenProvider: myProvider, tenantId: 't-99' });` [Cim Authentication v3.pdf p.5]. apiKey is removed.",
        "ground_truth": "Use tokenProvider and tenantId in SDK v3. apiKey configuration is removed.",
        "human_label": 1,
        "reason": "Correctly states SDK v3 tokenProvider syntax and notes removal of apiKey."
    }
]

for r in regression_specs:
    case_obj = {
        "case_id": r["case_id"],
        "trace_id": r["trace_id"],
        "is_regression": r["is_regression"],
        "mode": r["mode"],
        "question": r["question"],
        "required_version": r["required_version"],
        "context": r["context"],
        "answer": r["answer"],
        "ground_truth": r["ground_truth"]
    }
    unified_cases.append(case_obj)
    labels[r["case_id"]] = {
        "human_label": r["human_label"],
        "reason": r["reason"]
    }

print(f"Total unified cases: {len(unified_cases)}")
with open(OUTPUT_SET, "w", encoding="utf-8") as f:
    json.dump({"cases": unified_cases}, f, indent=2)

with open(OUTPUT_LABELS, "w", encoding="utf-8") as f:
    json.dump({
        "dataset": "eval_set_25.json (Q1-Q20 Gold Set + Q21-Q25 Regression Traces)",
        "criterion": "Helpfulness & Semantic Correctness (Single Binary: 1 = Pass, 0 = Fail)",
        "protocol": "Blind Human Hand-Labeling",
        "total_cases": 25,
        "labels": labels
    }, f, indent=2)

print("Saved unified eval_set_25.json and labels_25.json!")
