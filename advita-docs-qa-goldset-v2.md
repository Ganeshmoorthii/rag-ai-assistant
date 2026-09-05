# Advita / Cimplicity Docs Assistant — 20-Question Ground-Truth Set (v2)

**Corpus — these three documents only:**
- `BIZ` — Advita_DOCs.pdf (business workflow + data models + endpoints)
- `FE` — advita_FE.pdf (frontend structure & setup guide)
- `AUTH` — Cim_Authentication.pdf (authentication & authorization flow)

**Purpose:** a grading key for Week 5 error analysis. Each entry has the question, the answer
these documents actually support, and the specific facts an answer must contain.

**How to use it**
1. Run all 20 through your docs assistant. Log full traces (question, retrieved chunk_ids +
   scores, prompt version, model + params, raw output).
2. Let the app keep serving real traffic all week.
3. For the graded deliverable, draw your **seeded random sample of 20** from the whole trace
   log — not from this file. This is a curated set, which is Section 5's bonus challenge.
4. Use this file to check correctness while open-coding.

Difficulty: **E** single-chunk lookup · **M** multi-fact within one doc · **H** cross-document or trap

---

## Business workflow — `BIZ`

### Q1 — E
**Q:** What are the order types and what does each do?
**A:** BILL-RESTOCK — invoice sent and the warehouse ships replacement stock. BILL-ONLY —
invoice only. RESTOCK-ONLY — warehouse ships stock, no invoice. INSTRUMENT-QUOTE — price
quote generated, no fulfilment yet. DIRECT-SALE — straight sale, skips the surgery workflow.
**Must contain:** all five, with correct behaviour for each.

---

### Q2 — M
**Q:** What is a stickersheet and what happens to it in Cimplicity?
**A:** A physical label on every implant/device carrying lot/serial numbers. It gets peeled
off and attached to the patient's surgical record — a legal/regulatory requirement. The rep
photographs it and uploads it; the file goes to Azure Blob Storage with access control so
only the right rep/team can see it. Google Cloud Vision OCR reads the lot/serial numbers and
colour-codes annotations: blue for valid, red for discrepancy.
**Must contain:** the regulatory purpose, Azure Blob storage, Vision OCR, blue/red coding.

---

### Q3 — M
**Q:** How does AI verification of an order work, and what does `verificationStatus` mean?
**A:** On submit, `POST /orders/verification` sends the stickersheet image to Google Gemini,
which compares the serial numbers on the image against the order's `billingItems`. A match
sets `verificationStatus = COMPLETED`; a mismatch creates a VerificationDiscrepancy with
reason, serialNumber and status. `SKIPPED` means there was no stickersheet or the rep skipped
it — which is why every restock-only order shows SKIPPED: there is nothing to verify. The
example failure given is an OCR misread of `S` as `5`.
**Must contain:** Gemini, the two statuses, and why restock-only orders are always SKIPPED.

---

### Q4 — H (trap)
**Q:** Which ERP does the EBI module pull inventory data from?
**A:** SAP. EBI pulls from SAP's BI system (Webi) and the MSSQL data warehouse, then
normalises the raw XML into clean camelCase JSON for the frontend. QAD is the *other* ERP —
orders are written to QAD after creation, PO updates sync back to it, and inventory transfers
are synced with it. Advita runs both, with Cimplicity as the middle layer.
**Must contain:** SAP for EBI inventory, with QAD correctly distinguished rather than swapped.

---

### Q5 — M
**Q:** How does a ShippingItem get approved or rejected?
**A:** If the item's location ends in `-L` it is loaner stock: `reviewReason = 'LOANER'`,
`status = PENDING_APPROVAL`, and it needs human approval. Otherwise it is normal consignment
and the system checks the `restockMax` table for that `itemNumber + agencyCode`. If
`quantity <= max` it is APPROVED with `approvalReason = "Healthy target levels"`; if over, it
is REJECTED with `rejectionReason = "Not at target kit level"`. The `calculationTrail` field
logs the whole decision.
**Must contain:** the `-L` branch, the restockMax comparison, `calculationTrail`.

---

### Q6 — M
**Q:** What's the difference between a BillingItem and a ShippingItem?
**A:** A BillingItem is a product **used** in surgery; it lives under BillingComponent, has
pricing (`price`, `customPrice`, `noCharge`, `isCap`), links to the stickersheet via `fileId`,
and has no approval flow or calculationTrail. A ShippingItem is a product to be **shipped
back** to the rep; it lives under ShippingComponent, has no pricing — just quantity — and does
have approval (`status`, `reviewReason`, `approvalReason`) and a `calculationTrail`. Both have
an `Item` attached holding the actual product details.
**Must contain:** used-vs-shipped, pricing vs approval, both carry an Item.

---

### Q7 — M
**Q:** Walk through the order lifecycle statuses.
**A:** DRAFT → SUBMITTED (rep submits via web or iOS) → ShippingItems are auto-approved or
flagged → APPROVED / PENDING_APPROVAL / REJECTED → `inQad = true` once synced to QAD ERP →
`inCsFax = true` once sent to the warehouse fax system.
**Must contain:** the ordered chain including both boolean flags at the end.

---

### Q8 — E
**Q:** What counts toward revenue reporting?
**A:** Only BILL-ONLY and BILL-RESTOCK orders, because those are the ones that actually
generate revenue. RESTOCK-ONLY is excluded — no money changes hands. Billing tiers are
Capped, Custom, Discounted and Base Price.
**Must contain:** the two included types and the reason RESTOCK-ONLY is out.

---

### Q9 — M
**Q:** What happens after a physical inventory audit finds a mismatch?
**A:** Missing items trigger an inventory transfer to cover the gap; excess items are logged
as excess. If the discrepancy is too large, commission is deducted from the rep at
`Item Cost × 1.4`. The hierarchy is Audit → AgencyAudit (per agency) → LocationAudit (per
storage location) → AuditItem (each item counted) → Discrepancy → Transfer.
**Must contain:** missing→transfer, excess→logged, the ×1.4 multiplier.

---

### Q10 — M
**Q:** How are restock max levels set and used?
**A:** The `RestockMax` table holds `itemNumber`, `agencyCode` and `max` — the ceiling for how
much of an item an agency may hold. On a restock request the system looks up restockMax for
that item + agency, checks current inventory from EBI/SAP, and approves if
`currentInventory + requested <= max`, otherwise rejects and tells the rep to move inventory
within the agency instead. Maxes are loaded via `POST /demandPlanning/load/max` (manual Excel
upload) or `GET /demandPlanning/load/max` (auto-pull from SharePoint).
**Must contain:** the three columns, the comparison, both endpoints.

---

### Q11 — E
**Q:** What sections appear in the Action Center and what does each show?
**A:** Needs Billing (surgeries that happened but aren't billed), Missing PO (orders with no
purchase order number), Backorders (items out of stock waiting to ship), Restocks (pending
restock shipments), Stickersheet Inbox (uploaded stickersheets waiting to be processed).
Everything is exportable as PDF or Excel.
**Must contain:** all five sections with correct descriptions.

---

### Q12 — H (trap)
**Q:** Does `GET /ebi/locations` return loaner locations?
**A:** No. All standard inventory queries exclude loaner (`-L`) locations by default, so
normal inventory calculations are based on consignment stock only. Loaner stock is
higher-control inventory borrowed from a `-L` location and needs manager approval before it
ships.
**Must contain:** the exclusion is the default, and the consignment-only consequence.
**Trap:** a plausible-sounding "yes, it returns all locations" is exactly the wrong answer.

---

## Frontend — `FE`

### Q13 — M
**Q:** What are the entry point flows for native versus web?
**A:** Native: `index.js` registers the app component → `root/RootViewController.tsx`
initialises services and providers → `choreograph/Choreograph.tsx` sets up React Navigation →
`modules/*` feature screens. Web: `index.html` provides the DOM root → `index.web.js` mounts
the React app → `root/RootViewController.web.tsx` initialises web-specific services →
`choreograph/Choreograph.web.tsx` sets up web routing → `web/pages/*` or `modules/*`.
**Must contain:** both chains in order, with the correct `.web` variants on the web side.

---

### Q14 — E
**Q:** What are the steps to add a new screen?
**A:** Create a folder in `modules/[feature]/screens/`, create the component file
`MyScreen.tsx`, add the route in `choreograph/AppScreens.ts`, then add the navigation type in
`choreograph/AppScreenProps.ts`.
**Must contain:** all four steps, and the two distinct choreograph files.

---

### Q15 — M
**Q:** How does platform-specific file resolution work?
**A:** A component can exist as `MyComponent.tsx` (shared across iOS and Android),
`MyComponent.web.tsx`, `MyComponent.ios.tsx` or `MyComponent.android.tsx` — the last two are
rarely used. Resolution priority is exact platform match first (`.web.tsx`, `.ios.tsx`,
`.android.tsx`), then the shared `.tsx` file.
**Must contain:** the variants and the two-step priority order.

---

### Q16 — M
**Q:** Which services live in the services layer, and how does a screen access one?
**A:** `authentication/` (login, token refresh, user session), `bluetooth/` (BLE),
`code-scanner/` (QR and barcode via Vision Camera), `discount-pricing/`, `extraction/`
(ML-based document extraction using TensorFlow Lite), `keychain/` (secure credential storage),
plus `RehydrateService.ts` for state rehydration on app start. Services are injected via React
Context — exposed through `services/AppServices.tsx` and accessed via `ServicesContext.tsx`.
**Must contain:** the injection mechanism, not just the folder list.

---

### Q17 — E
**Q:** Which npm scripts run the web app, and what does each do?
**A:** `npm run web:dev` starts the dev server with hot module replacement on
`http://localhost:8080` (or the next available port) with source maps. `npm run web:prod`
runs an optimised production build served with the dev server, useful for testing.
`npm run web:dist` creates the optimised bundle in `dist/`, ready for deployment.
**Must contain:** all three, distinguished correctly — `web:prod` is not the deployment build.

---

## Authentication — `AUTH`

### Q18 — M
**Q:** What are the three ways a request can authenticate?
**A:** A user JWT as `Authorization: Bearer <jwt>`, issued by Azure AD and checked by the
`requireAuthentication` middleware. A Cimplicity API key in mixed mode as
`Authorization: Bearer cim_<hex>`, also handled by `requireAuthentication`. A pure machine API
key as `X-API-Key: cim_<hex>`, handled by `requireApiKey`. Keys are recognised by the `cim_`
prefix and validated against the `apiKey` table by SHA-256 hash match plus `isActive` and
`expiresAt` checks.
**Must contain:** all three header shapes with the right middleware for each.

---

### Q19 — M
**Q:** Walk through `verifyToken`.
**A:** Three steps. First a cache lookup via `getCachedJwtPayload(token)` in `jwtCache.ts` —
Redis-backed, SHA-256 hashed key, TTL aligned to the JWT `exp` and capped at 60 minutes. On a
cache miss, JWKS verification against `config.oidc.jwksUrl` using `jose.jwtVerify` with
`audience = config.oidc.jwtAudience` and `issuer = config.oidc.jwtIssuer`. Then the verified
payload is written back to Redis. If `config.oidc.disableSecurityCheck` is true — dev only —
signature, issuer and audience checks are skipped and the payload is decoded directly; this
must be false in production.
**Must contain:** the three steps in order, plus the disableSecurityCheck caveat.

---

### Q20 — H (trap)
**Q:** Do API keys go through the permission system?
**A:** No — they bypass it and act as a superuser, and the docs warn to issue them sparingly.
A validated key binds the request to a synthetic system user with `id: 'api-key-system'` whose
`hasPermission` always returns true. Keys are `cim_` plus 64 hex characters (256 bits of
entropy), stored only as a SHA-256 `keyHash` with a 12-character `keyPrefix`, and the raw key
is returned exactly once at creation. `validateApiKey` hashes the incoming key, looks it up by
`keyHash` with `isActive = true`, rejects if `expiresAt` has passed, and stamps `lastUsedAt`.
**Must contain:** the bypass/superuser fact — that is the load-bearing part.
**Trap:** an answer that describes key validation carefully but implies keys still get
permission-checked is wrong in the way that matters.

---

## Coverage

| Source | Questions | Count |
|---|---|---|
| `BIZ` — Advita_DOCs.pdf | Q1–Q12 | 12 |
| `FE` — advita_FE.pdf | Q13–Q17 | 5 |
| `AUTH` — Cim_Authentication.pdf | Q18–Q20 | 3 |

| Difficulty | Count |
|---|---|
| E — single lookup | 5 |
| M — multi-fact, one doc | 12 |
| H — trap | 3 |

Deliberate traps: Q4 (SAP vs QAD swap), Q12 (`-L` exclusion), Q20 (API key superuser bypass).
Q3 and Q6 test whether the assistant carries a distinction across a table rather than
collapsing two similar entities.

## Trace fields to log

Per Requirement 1, each trace needs enough to replay from the trace alone: `trace_id`,
`timestamp`, `question`, `prompt_version`, `retrieved_chunk_ids` + scores, `model` + params
(temperature, max_tokens), `raw_output`, `latency_ms`, `source_doc`. If a field turns out to be
missing when you go to replay, add it, note that you added it, and record what you could not
reconstruct.
