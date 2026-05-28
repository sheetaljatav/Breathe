# Decisions

The brief leaves a lot open on purpose. This document lists the meaningful ambiguities, what was decided, the reasoning behind the decision, and the question that would have gone back to the PM with more time.

Each entry follows the same shape:

- **Question** — the ambiguity in the brief
- **Decision** — what was built
- **Reasoning** — why, including the alternatives that were considered
- **Open question** — what to ask the PM

---

### 1. Which SAP export format to accept

**Decision.** SE16N flat-file CSV: semicolon-delimited, UTF-8 with BOM, German decimal commas, `DD.MM.YYYY` dates, German column headers.

**Reasoning.** SE16N is what an analyst-accessible SAP output actually looks like. IDoc, BAPI, and OData all require system-level access to the customer's SAP instance — that doesn't generalize across customers and isn't a prototype motion (see `TRADEOFFS.md` #1). Choosing SE16N CSV is choosing the format an analyst-facing tool actually sees in v1.

**Open question.** Do any pilot customers ship IDocs today? If yes, a thin IDoc adapter would convert to the same `SourceRecord` payload shape, and the parser pipeline downstream stays identical.

---

### 2. Which utility-data format to accept (CSV, PDF, or both)

**Decision.** Both. Portal CSV is primary; text-extractable PDF via pdfplumber is secondary. Both flow through the same downstream pipeline and produce identical `SourceRecord` shapes.

**Reasoning.** Real facilities teams send both: CSV when they have portal access, PDF when they only have the emailed monthly statement. Shipping only one feels like a half-product. The marginal cost of supporting both is low because everything from `SourceRecord` onward is shared between them.

**Open question.** What's the actual format split among pilot customers? If it's heavily skewed to one, the effort spent on per-utility PDF templates should follow.

---

### 3. Concur integration vs. paste

**Decision.** A JSON-paste endpoint that accepts the Concur Reporting v4 `/reports/{id}/expenses` response shape.

**Reasoning.** Concur OAuth onboarding requires a corporate-customer relationship with SAP Concur and per-tenant App Center approval. That's a sales motion, not a prototype motion. The parser that ships here is exactly the one a real integration would use — only the transport (paste vs. OAuth) changes. The choice was to make the parser the visible deliverable, not the OAuth gymnastics around it.

**Open question.** Is there a sandbox Concur tenant accessible for development? With one, OAuth + a paginator could sit on top of the existing parser as a separate orchestration layer.

---

### 4. Sync ingestion in the request, or async via a worker

**Decision.** Async. Celery worker, Redis broker. Upload returns 202 with a `batch_id`; the frontend polls `/api/batches/:id/` every two seconds.

**Reasoning.** Real ESG ingestion files run between 10k and 500k rows. Synchronous parsing would block requests, time out under Render's 30-second free-tier limit, and force a re-upload when the connection flakes. A worker is the standard shape for Django async work and is what production would run regardless of platform.

**Open question.** What's the expected p95 file size from the first cohort of customers? That determines whether free-tier Redis is enough or whether the paid plan should be in the budget from day one.

---

### 5. Multi-tenancy enforcement (application, database, or both)

**Decision.** Both. `TenantQuerySet` raises on unscoped queries at the ORM layer. Postgres RLS policies enforce isolation at the database layer.

**Reasoning.** Cross-tenant leakage is the worst-case bug this product can ship. Application-layer filtering catches the common case (a developer remembering to call `.for_org()`). RLS catches the cases the app layer can miss: raw SQL, ORM bypass, a future bug in the queryset helper. The cost is one migration (`core/0002_rls_policies`) and one middleware. It's a small price for the bug class with the highest blast radius.

**Open question.** Is there a regulated segment in the target market (FedRAMP, HIPAA-adjacent) where per-tenant schemas would be a requirement rather than a defensive layer? If so, separate schemas could go on top of RLS for that segment.

---

### 6. Audit immutability (model guards or database triggers)

**Decision.** Both, with the triggers as the load-bearing layer. `AuditLog.save()` and `.delete()` overrides raise at the model level. `BEFORE UPDATE` / `BEFORE DELETE` triggers raise at the database level for every role, superuser included.

**Reasoning.** Model-layer guards only catch the polite path (`.save()` / `.delete()`). They don't catch `objects.update(...)` or raw SQL. Triggers do. The choice of triggers over a role-based `REVOKE` matters because in development the app commonly runs as a privileged role, where `REVOKE` on table privileges is a no-op — triggers don't care about role.

**Open question.** Do auditors expect tamper-*evidence* (a hash chain over rows, signed checkpoints) on top of tamper-resistance? The current implementation is resistant. Evidence is straightforward to add — hash-chain `id || before || after` rolling forward — but shouldn't ship without a regulatory requirement to point at.

---

### 7. Optimistic vs. pessimistic locking on edits

**Decision.** Optimistic. `ActivityRecord.version` increments per save; `PATCH` requires `If-Match: <version>`; a mismatch returns 412 with the current state in the body.

**Reasoning.** Analysts work concurrently on overlapping queues. Pessimistic row locks (a `SELECT FOR UPDATE` held for the duration of a UI session) would be terrible for UX and require connection state the API layer shouldn't carry. Optimistic concurrency is the standard correctness move for shared editable records in queue tools; the cost is one extra header and a small dialog for the rare conflict.

**Open question.** What's the size of an analyst team sharing a queue? Three analysts rarely collide. Thirty would benefit from presence indicators — "someone else is editing this" — surfaced *before* a conflict, the way Google Docs does.

---

### 8. Emission factors pinned vs. looked up at query time

**Decision.** Pinned. `ActivityRecord.emission_factor` is an FK populated at normalization time; `emissions_kg_co2e` is computed and stored at the same time.

**Reasoning.** When DEFRA or EPA publish updated factors next year, last year's calculations cannot drift. Auditors need stable historical numbers. Recalculation with new factors needs to be an *explicit* operation that creates new audit entries — never a silent re-derivation.

**Open question.** Would customers want a "what would this report look like under current factors" view? The math is `value * current_factor.kg_co2e_per_unit`, which is straightforward. It's a feature, not a default.

---

### 9. `approved` vs. `locked` as distinct states

**Decision.** Two states. `approved` is the analyst's sign-off; `locked` is the admin's audit freeze.

**Reasoning.** Analysts approve as part of their daily workflow ("I've reviewed this, it looks right"). Locking is the irreversible commitment to a snapshot that will be sent to auditors. The two are different actions, taken by different roles, at different times. Collapsing them ("approved = locked") would mean analysts can't revise yesterday's approval before audit, which is the wrong product call.

**Open question.** Who holds lock authority at pilot customers — the head of sustainability, the CFO? If it's a CFO-level decision, `admin` is too broad as a role; a third role would be appropriate.

---

### 10. Org switcher (header, subdomain, or session-persisted)

**Decision.** Header (`X-Org-ID`), set by the frontend and persisted to `localStorage`. The backend validates membership on every request.

**Reasoning.** Subdomains (`acme.breathe-esg.com`) are nicer URLs but require DNS work and a separate CSRF / cookie story for each tenant. Session-only state makes the org context invisible to debugging and harder to test. Header-based is the cheapest implementation that's also the easiest to audit — any HTTP trace shows which org the request ran against.

**Open question.** Are pilot customers expecting strict per-user single-org accounts for security reasons? Several enterprise SaaS products work that way. If so, the switcher would be hidden and org pinned server-side.

---

### 11. Anomaly hint computation (stored, materialized, or on-read)

**Decision.** Computed on read.

**Reasoning.** Storing hints means writing them at ingest *and* rewriting them every time the rule logic changes. Materialized views add refresh management. Computation on read costs one query per detail-page open, which is cheap (the `ar_queue_idx` covers it). The rules can evolve without a migration.

**Open question.** What's the expected queue size per analyst per day? At 10k+ rows of pending review, hints should be cached per batch (computed once on parse, refreshed on edit).

---

### 12. Plant-code and airport lookups (per-org or global)

**Decision.** `PlantCode` is per-org. `Airport` is global.

**Reasoning.** SAP plant numbers are customer-internal identifiers. `1000` at Acme is "Düsseldorf"; `1000` at Globex could be anything else. Airports are an international standard (IATA). The schema reflects that.

**Open question.** Should customers manage plant-code lookups themselves through a settings UI, or is it fine for the implementation team to maintain it as part of onboarding? Today it's onboarding-only.

---

### 13. Demo deployment vs. production deployment

**Decision.** Same `render.yaml`, same code, same migrations. The differences are configuration: in production, `DATABASE_URL` should point at a non-superuser role (so RLS forces apply), `SENTRY_DSN` is set, and `ALLOWED_HOSTS` is the real domain. The demo runs entirely on Render free-tier services (web + worker + Postgres + Redis), with seeded data and demo accounts visible on the login page.

**Reasoning.** A demo that diverges from production architecture defeats the point of a demo. Render's free Redis (25 MB) is enough for prototype task volume. For real production traffic the $7/month Redis plan would be appropriate, but the architecture doesn't change.

**Open question.** What's the production scale target? If sustained task throughput is low and individual files fit inside Render's free Postgres (1 GB, 90-day expiry), free-tier is workable. For serious volume, Neon Postgres (no expiry) plus Upstash Redis is a cost-effective combination that stays on free tiers.

---

## On what isn't in this list

A few decisions weren't worth listing here because they aren't ambiguities the brief raised. The choice of TanStack Query over Redux for client state, Tailwind over CSS Modules, Vite over Next.js — these were judgment calls but they don't connect to anything the rubric weighs. They're visible in the code; they aren't worth defending here.

The decisions worth defending are the ones above. If a reviewer disagrees with any of them, the open question per entry is the conversation that should follow.
