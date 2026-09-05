"""Trace dataset generator for Week 5 Error Analysis (Developer Documentation).

Generates 100 replayable, realistic developer documentation traces into
`backend/data/traces.jsonl`, including metadata:
  - trace_id
  - timestamp
  - original_question
  - prompt_version
  - system_prompt
  - model & model_params
  - config
  - retrieved_chunks
  - raw_output / answer
  - stages & timings
  - is_demo (for curated demo set)
"""

import json
import os
import random
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "traces.jsonl")

SYSTEM_PROMPT = (
    "You are a helpful assistant answering questions using only the provided "
    "context from the user's documents. If the answer isn't in the context, "
    "say you don't know. Cite the filename and page number when relevant."
)

# 100 Traces covering developer documentation topics
# Curated ground truth data reflecting realistic DX questions and failure patterns
TRACES_DATA = [
    # 1. v2_signature_returned_for_v3_query (Outdated SDK signatures)
    {
        "id": "tr_001",
        "question": "How do I initialize the Cimplicity AuthClient in v3 SDK?",
        "expected_mode": "v2_signature_returned_for_v3_query",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p2_c1",
                "filename": "Cim Authentication v2.pdf",
                "page": 2,
                "score": 0.88,
                "text": "AuthClient initialization (v2.4):\n`const client = new AuthClient({ apiKey: 'cim_123', secret: 'abc' });`\nNote: Deprecated in v3."
            },
            {
                "id": "cim_auth_p5_c2",
                "filename": "Cim Authentication v3.pdf",
                "page": 5,
                "score": 0.74,
                "text": "AuthClient initialization (v3.0+):\n`const client = new AuthClient({ tokenProvider: myProvider, tenantId: 't-99' });`\nAPI Key options removed."
            }
        ],
        "answer": "To initialize the AuthClient, use `const client = new AuthClient({ apiKey: 'cim_123', secret: 'abc' });` [Cim Authentication v2.pdf p.2]."
    },
    {
        "id": "tr_002",
        "question": "What parameters does `requireApiKey()` accept in v3?",
        "expected_mode": "v2_signature_returned_for_v3_query",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p4_c1",
                "filename": "Cim Authentication.pdf",
                "page": 4,
                "score": 0.85,
                "text": "requireApiKey(req, res, next) middleware checks header 'x-api-key'. Legacy parameter list."
            }
        ],
        "answer": "The `requireApiKey` middleware accepts `(req, res, next)` positional parameters [Cim Authentication.pdf p.4]."
    },
    {
        "id": "tr_003",
        "question": "How do I register an async event listener in SDK v3?",
        "expected_mode": "v2_signature_returned_for_v3_query",
        "retrieved_chunks": [
            {
                "id": "advita_events_p1",
                "filename": "Advita SDK v2.pdf",
                "page": 1,
                "score": 0.82,
                "text": "Registering listeners: `sdk.on('event', callbackFunc)`."
            }
        ],
        "answer": "You register event listeners using `sdk.on('event', callbackFunc)` [Advita SDK v2.pdf p.1]."
    },

    # 2. omitted_prerequisite_header_or_import (Missing required setup/headers)
    {
        "id": "tr_004",
        "question": "How do I make an API call to user impersonation endpoint?",
        "expected_mode": "omitted_prerequisite_header_or_import",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p3_c1",
                "filename": "Cim Authentication.pdf",
                "page": 3,
                "score": 0.81,
                "text": "User Impersonation endpoint: POST /api/v1/impersonate. Specify targetUserId in JSON body."
            }
        ],
        "answer": "Send a POST request to `/api/v1/impersonate` with `targetUserId` in the request body [Cim Authentication.pdf p.3]."
    },
    {
        "id": "tr_005",
        "question": "How do I call the Backorders Action Center endpoint from node?",
        "expected_mode": "omitted_prerequisite_header_or_import",
        "retrieved_chunks": [
            {
                "id": "advita_docs_p13_c1",
                "filename": "Advita DOCs.pdf",
                "page": 13,
                "score": 0.79,
                "text": "Action Center endpoint: GET /ebi/backorders returns all out-of-stock items."
            }
        ],
        "answer": "Make a GET request to `/ebi/backorders` to fetch items waiting to ship [Advita DOCs.pdf p.13]."
    },
    {
        "id": "tr_006",
        "question": "How do I sync order details with QAD module?",
        "expected_mode": "omitted_prerequisite_header_or_import",
        "retrieved_chunks": [
            {
                "id": "advita_docs_p4_c2",
                "filename": "Advita DOCs.pdf",
                "page": 4,
                "score": 0.83,
                "text": "QAD Module sync: Call `qadSyncService.syncOrder(orderId)`."
            }
        ],
        "answer": "Invoke `qadSyncService.syncOrder(orderId)` to write the order to QAD [Advita DOCs.pdf p.4]."
    },

    # 3. wildcard_and_special_char_token_dropped (Special characters / tokenization failures)
    {
        "id": "tr_007",
        "question": "What does the wildcard * mean in a permission string?",
        "expected_mode": "wildcard_and_special_char_token_dropped",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p8_c1",
                "filename": "Cim Authentication.pdf",
                "page": 8,
                "score": 0.42,
                "text": "Permission syntax: string matching. Standard permissions use domain:action format."
            }
        ],
        "answer": "Permission strings use domain:action format for matching standard permissions [Cim Authentication.pdf p.8]."
    },
    {
        "id": "tr_008",
        "question": "What does a location ending in -L mean in inventory?",
        "expected_mode": "wildcard_and_special_char_token_dropped",
        "retrieved_chunks": [
            {
                "id": "advita_docs_p9_c1",
                "filename": "Advita DOCs.pdf",
                "page": 9,
                "score": 0.51,
                "text": "Location codes format: 4-digit agency code followed by zone letter."
            }
        ],
        "answer": "Locations specify agency code followed by zone letters [Advita DOCs.pdf p.9]."
    },
    {
        "id": "tr_009",
        "question": "What prefix identifies a Cimplicity API key?",
        "expected_mode": "wildcard_and_special_char_token_dropped",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p2_c2",
                "filename": "Cim Authentication.pdf",
                "page": 2,
                "score": 0.55,
                "text": "Authentication keys: API keys are strings generated in the admin portal."
            }
        ],
        "answer": "API keys are generated strings in the admin portal [Cim Authentication.pdf p.2]."
    },

    # 4. numeric_status_code_confusion (HTTP 401 vs 403 confusion)
    {
        "id": "tr_010",
        "question": "When does the API return 403 versus 401?",
        "expected_mode": "numeric_status_code_confusion",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p9_c1",
                "filename": "Cim Authentication.pdf",
                "page": 9,
                "score": 0.77,
                "text": "Error Handling: Returns HTTP status response on request failure."
            }
        ],
        "answer": "The API returns 401 or 403 when requests fail authentication or authorization checks [Cim Authentication.pdf p.9]."
    },
    {
        "id": "tr_011",
        "question": "What status code is returned when JWT token is expired?",
        "expected_mode": "numeric_status_code_confusion",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p6_c2",
                "filename": "Cim Authentication.pdf",
                "page": 6,
                "score": 0.72,
                "text": "JWT Validation: If validation fails or permission check fails, status 403 Forbidden is returned."
            }
        ],
        "answer": "An expired JWT returns 403 Forbidden [Cim Authentication.pdf p.6]."
    },
    {
        "id": "tr_012",
        "question": "What error code indicates missing purchase order on surgery billing?",
        "expected_mode": "numeric_status_code_confusion",
        "retrieved_chunks": [
            {
                "id": "advita_docs_p5_c3",
                "filename": "Advita DOCs.pdf",
                "page": 5,
                "score": 0.69,
                "text": "Billing errors: Returns code 400 Bad Request when PO is missing."
            }
        ],
        "answer": "It returns HTTP 400 Bad Request [Advita DOCs.pdf p.5]."
    },

    # 5. partial_multihop_context_truncation (Multi-system query missing 2nd part)
    {
        "id": "tr_013",
        "question": "What are the two ERP systems and which module talks to each?",
        "expected_mode": "partial_multihop_context_truncation",
        "retrieved_chunks": [
            {
                "id": "advita_docs_p4_c1",
                "filename": "Advita DOCs.pdf",
                "page": 4,
                "score": 0.89,
                "text": "Advita uses SAP and QAD. Cimplicity talks to both. Module QAD writes orders to QAD."
            },
            {
                "id": "advita_docs_p4_c2",
                "filename": "Advita DOCs.pdf",
                "page": 4,
                "score": 0.86,
                "text": "PO updates sync back to QAD."
            }
        ],
        "answer": "The two ERP systems are SAP and QAD. Module QAD communicates with QAD [Advita DOCs.pdf p.4]."
    },
    {
        "id": "tr_014",
        "question": "What is the discrepancy commission formula AND how are loaner items approved?",
        "expected_mode": "partial_multihop_context_truncation",
        "retrieved_chunks": [
            {
                "id": "advita_docs_p5_c1",
                "filename": "Advita DOCs.pdf",
                "page": 5,
                "score": 0.88,
                "text": "Discrepancy penalty: Item Cost x 1.4 deducted from rep commission."
            }
        ],
        "answer": "The discrepancy formula is Item Cost x 1.4 deducted from rep commission [Advita DOCs.pdf p.5]."
    },
    {
        "id": "tr_015",
        "question": "Where is JWT cached, what is its TTL, AND what scopes are requested?",
        "expected_mode": "partial_multihop_context_truncation",
        "retrieved_chunks": [
            {
                "id": "cim_auth_p6_c1",
                "filename": "Cim Authentication.pdf",
                "page": 6,
                "score": 0.87,
                "text": "JWT payload is cached in Redis with TTL capped at 60 minutes."
            }
        ],
        "answer": "JWT is cached in Redis with a TTL capped at 60 minutes [Cim Authentication.pdf p.6]."
    }
]

# Expand to 100 items by generating realistic variants covering developer documentation traces
def build_full_trace_dataset():
    random.seed(42) # Seed for deterministic dataset generation
    full_traces = []
    
    # Base modes distribution template across 100 items:
    # Mode 1: v2_signature_returned_for_v3_query (30 traces = 30%)
    # Mode 2: omitted_prerequisite_header_or_import (25 traces = 25%)
    # Mode 3: wildcard_and_special_char_token_dropped (20 traces = 20%)
    # Mode 4: numeric_status_code_confusion (15 traces = 15%)
    # Mode 5: partial_multihop_context_truncation (10 traces = 10%)

    mode_templates = {
        "v2_signature_returned_for_v3_query": [
            ("How do I initialize AuthClient in v3?", "Cim Authentication v2.pdf", 2, "const client = new AuthClient({ apiKey: 'cim_key' });", "AuthClient init uses apiKey in config [Cim Authentication v2.pdf p.2]"),
            ("What is the function signature for `verifyToken()` in v3 SDK?", "Cim Authentication.pdf", 4, "verifyToken(token, secretKey, options)", "`verifyToken` takes positional token and secretKey arguments [Cim Authentication.pdf p.4]"),
            ("How to create an audit task using v3 API?", "Advita DOCs.pdf", 6, "createAuditTask(agencyId, repId)", "Use `createAuditTask(agencyId, repId)` [Advita DOCs.pdf p.6]"),
            ("What is the v3 method for restocking inventory?", "Advita DOCs.pdf", 10, "restockItem(itemId, qty, legacyFlag)", "Call `restockItem(itemId, qty, legacyFlag)` [Advita DOCs.pdf p.10]"),
            ("How do I call `getBackorders()` in SDK v3?", "Advita FE.pdf", 3, "getBackorders(agencyId)", "`getBackorders` accepts single agencyId parameter [Advita FE.pdf p.3]")
        ],
        "omitted_prerequisite_header_or_import": [
            ("How do I make an HTTP request to /api/v1/impersonate?", "Cim Authentication.pdf", 3, "POST /api/v1/impersonate body: { userId: '123' }", "Send POST to /api/v1/impersonate with target userId [Cim Authentication.pdf p.3]"),
            ("How to fetch revenue analytics endpoint?", "Advita DOCs.pdf", 5, "GET /api/revenue returns monthly revenue stats", "Call GET /api/revenue endpoint [Advita DOCs.pdf p.5]"),
            ("How to invoke physical inventory reconciliation API?", "Advita DOCs.pdf", 4, "POST /api/inventory/reconcile with auditId", "Submit POST request to /api/inventory/reconcile [Advita DOCs.pdf p.4]"),
            ("How to update purchase order status via REST?", "Advita DOCs.pdf", 8, "PUT /api/orders/{id}/po with poNumber", "Send PUT request to /api/orders/{id}/po [Advita DOCs.pdf p.8]"),
            ("How to query Action Center backorders endpoint?", "Advita DOCs.pdf", 13, "GET /ebi/backorders returns pending backorders", "Query GET /ebi/backorders endpoint [Advita DOCs.pdf p.13]")
        ],
        "wildcard_and_special_char_token_dropped": [
            ("What does wildcard * mean in permission strings?", "Cim Authentication.pdf", 8, "Permission strings use format resource:action", "Permission strings use resource:action format [Cim Authentication.pdf p.8]"),
            ("What does location code suffix -L stand for?", "Advita DOCs.pdf", 9, "Location codes start with 4-digit agency identifier", "Location codes represent agency IDs [Advita DOCs.pdf p.9]"),
            ("What does prefix cim_ signify on API keys?", "Cim Authentication.pdf", 2, "API keys are generated in security portal", "API keys are generated strings [Cim Authentication.pdf p.2]"),
            ("What does option `--force-sync` do in CLI?", "Advita FE.pdf", 5, "CLI options accept flags for sync operations", "CLI options control sync behavior [Advita FE.pdf p.5]"),
            ("What does setting `disableSecurityCheck=true` do?", "Cim Authentication.pdf", 6, "Security checks control route validation", "Security checks validate incoming requests [Cim Authentication.pdf p.6]")
        ],
        "numeric_status_code_confusion": [
            ("When does the auth server return 403 versus 401?", "Cim Authentication.pdf", 9, "HTTP error codes report failure status", "Returns HTTP 401 or 403 status codes [Cim Authentication.pdf p.9]"),
            ("What status code is thrown on expired JWT token?", "Cim Authentication.pdf", 6, "Validation failures return HTTP 403", "Expired JWT returns HTTP 403 Forbidden [Cim Authentication.pdf p.6]"),
            ("What status code is returned for missing API key?", "Cim Authentication.pdf", 4, "Missing keys return standard HTTP authorization error", "Returns 403 Forbidden [Cim Authentication.pdf p.4]"),
            ("What error code is returned when restock order verification fails?", "Advita DOCs.pdf", 12, "Verification status returns error status", "Returns status code 400 [Advita DOCs.pdf p.12]")
        ],
        "partial_multihop_context_truncation": [
            ("What are the two ERP systems and which module talks to each?", "Advita DOCs.pdf", 4, "Advita uses SAP and QAD. Module QAD handles QAD sync.", "The ERP systems are SAP and QAD, with Module QAD managing QAD [Advita DOCs.pdf p.4]"),
            ("Where is JWT cached, what is TTL, AND what scopes are required?", "Cim Authentication.pdf", 6, "JWT is cached in Redis with max TTL 60 minutes.", "JWT is cached in Redis with a 60 min TTL [Cim Authentication.pdf p.6]"),
            ("What is commission discrepancy formula AND how is loaner approved?", "Advita DOCs.pdf", 5, "Discrepancy penalty is Item Cost x 1.4.", "Commission discrepancy penalty is Item Cost x 1.4 [Advita DOCs.pdf p.5]")
        ]
    }

    base_time = datetime(2026, 8, 25, 9, 0, 0)
    
    # Generate 100 traces
    idx = 1
    # 10 Curated demo questions (for bonus challenge)
    demo_indices = {1, 5, 12, 18, 25, 34, 45, 56, 78, 90}

    # Sequence of modes to hit target distribution:
    mode_distribution = (
        ["v2_signature_returned_for_v3_query"] * 30 +
        ["omitted_prerequisite_header_or_import"] * 25 +
        ["wildcard_and_special_char_token_dropped"] * 20 +
        ["numeric_status_code_confusion"] * 15 +
        ["partial_multihop_context_truncation"] * 10
    )
    random.shuffle(mode_distribution)

    for mode in mode_distribution:
        tr_id = f"tr_{idx:03d}"
        template = random.choice(mode_templates[mode])
        q, fname, page, chunk_text, ans = template
        
        # Add slight variation to question text for realistic log feeling
        q_var = f"{q}" if idx % 2 == 0 else f"{q.lower()}"
        
        trace = {
            "trace_id": tr_id,
            "timestamp": (base_time + timedelta(minutes=idx * 45)).isoformat(),
            "original_question": q_var,
            "prompt_version": "v1.0.0",
            "system_prompt": SYSTEM_PROMPT,
            "model": "llama-3.3-70b-versatile",
            "model_params": {
                "temperature": 0.0,
                "max_tokens": 1024,
                "top_p": 1.0
            },
            "config": {
                "top_k": 3,
                "hybrid": True,
                "rerank": False,
                "rewrite": False,
                "mmr": False
            },
            "retrieved_chunks": [
                {
                    "id": f"chk_{tr_id}_1",
                    "filename": fname,
                    "page": page,
                    "score": round(random.uniform(0.70, 0.92), 4),
                    "text": chunk_text
                }
            ],
            "raw_output": ans,
            "answer": ans,
            "expected_mode": mode,
            "is_demo": idx in demo_indices,
            "stages": [
                {
                    "stage": "dense_search",
                    "query": q_var,
                    "returned": 3,
                    "top": [{"rank": 1, "id": f"chk_{tr_id}_1", "filename": fname, "page": page, "score": 0.85, "preview": chunk_text[:80]}]
                },
                {
                    "stage": "bm25_search",
                    "query": q_var,
                    "returned": 3,
                    "top": [{"rank": 1, "id": f"chk_{tr_id}_1", "filename": fname, "page": page, "score": 4.12, "preview": chunk_text[:80]}]
                }
            ],
            "timings_ms": {
                "dense_search": round(random.uniform(80, 150), 1),
                "bm25_search": round(random.uniform(10, 35), 1),
                "total": round(random.uniform(100, 185), 1)
            }
        }
        full_traces.append(trace)
        idx += 1

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for t in full_traces:
            f.write(json.dumps(t) + "\n")
            
    print(f"Successfully generated {len(full_traces)} traces in {OUTPUT_PATH}")

if __name__ == "__main__":
    build_full_trace_dataset()
