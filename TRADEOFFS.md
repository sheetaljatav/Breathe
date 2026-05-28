# Tradeoffs

Three things this prototype deliberately does not include. Each is left out for a product, architecture, or correctness reason — not for time. Each would still be skipped with more time available.

---

## 1. No auto-pull connectors for SAP, Concur, or utility APIs

### What's missing

Direct integrations that authenticate against a customer's SAP system (IDoc listener, OData consumer, BAPI/RFC client), against their Concur tenant (OAuth + Reporting v4 paginator), or against a utility's portal or API.

### Why it isn't here

Connector reliability is a per-customer problem, not a per-vendor problem. Each enterprise customer has:

- A different SAP transport configuration: different table and field names, different IDoc message types, different OData services activated.
- A different Concur reporting build: different segment-type customizations, different approval workflows, a different OAuth scope set.
- A different utility account: different rate classes, different portal patterns (some give CSV, some PDF only, some give an API), and a different facilities-team operating model.

A "generic" connector is a false promise of compatibility. It tends to ship fine on the first customer, break on the third, and cost more engineering by the fifth than it saves. The industry pattern here is unambiguous: large ESG platforms (Watershed, Persefoni, Sweep) all ship manual ingestion as primary and treat per-customer connectors as paid onboarding work.

### What's there instead

The ingestion layer is parser-shaped, not connector-shaped. Parsers take bytes (`parse(data: bytes) -> ParseResult`). How those bytes arrive — file upload, S3 drop, SFTP pickup, scheduled API pull — is a thin orchestration layer added per customer. The data model and the parsers themselves don't change; only the bytes-delivery mechanism does.

### What would come first if this expanded

Not a generic connector framework. The S3 drop pattern would: a customer-specific bucket where their internal team drops SAP exports on a schedule, with an orchestrator that picks up new files and enqueues `parse_batch`. That's a few days of work, generalizes across customers, and doesn't make false promises about API compatibility.

---

## 2. Rule-based anomaly detection, not ML

### What's missing

A model — anomaly detection, classification, or LLM-as-judge — that scores activity records for review priority. No autoencoder, no isolation forest, no embedding-based categorization off the material short text.

### Why it isn't here

Audit-grade emissions data has to be explainable. The relevant audiences are:

- The internal analyst defending a flag to a compliance team.
- The external auditor reviewing the year's emissions report.
- The regulator who may eventually ask "show me how this number was produced".

A flag of the form "value 1,075,000 kWh is 12× the 90-day rolling median (89,500 kWh) for meter M-AC-ATL-002" is defensible to all three. A flag of the form "model confidence 0.83" is defensible to none of them. The opacity of even a well-calibrated model compounds compliance risk in a way that's hard to walk back once it ships.

There is also a false-negative class problem. With rules, the set of patterns missed is enumerable — it's the code in `emissions/anomaly.py`. With a model, the set of false negatives isn't enumerable by construction, which makes regulatory review materially harder.

### What's there instead

Three rules, computed on read, each producing a hint with a stable code, a human-readable message, and the numbers behind it:

- `ROLLING_MEDIAN_OUTLIER` — value greater than 5× the rolling 90-day median for the same (category, facility).
- `UNRESOLVABLE_LOOKUP` — placeholder for unmapped plant codes and missing airports.
- `PERIOD_OVERLAP` — billing period overlaps an already-approved record (the double-counting risk).

The reasoning string the rule produces is the same string an analyst would write in their own notes. That's the bar.

### What would come first if this expanded

Not ML. More rules. The next two on the list:

- Year-over-year deviation — value differs by more than X% from the same period the prior year, accounting for capacity changes.
- Cross-meter consistency — for facilities with multiple meters, sum-of-meter rows that don't match the bill-aggregate row.

ML earns a place when (a) there's enough labeled flag/clear data per category, and (b) per-rule false-positive analysis shows ML reduces analyst burden more than the explainability cost. Neither holds at v1.

---

## 3. Explicit per-pair unit conversions, no general engine

### What's missing

A general unit-conversion engine like `pint` that converts between arbitrary dimensions via registered base units and derived relationships.

### Why it isn't here

General engines produce wrong-but-plausible results across dimension boundaries. Two specific failure modes matter for emissions:

1. **Mass to volume without a per-fuel density assumption.** Diesel and petrol have different densities (~0.835 kg/L for diesel, ~0.745 kg/L for petrol). A general engine asked to convert "1000 kg" to "L" needs a density. `pint` either refuses (forcing per-call density specification) or uses a default — and there isn't a defensible default density for "fuel". This is the kind of bug that's documented as a real failure mode in ESG vendor postmortems.

2. **MWh thermal vs. MWh electrical.** Both are energy. They are not interchangeable. A general engine doesn't carry the distinction; conversion logic for emissions has to.

For data that an auditor signs off on, correctness has to dominate coverage. An explicit per-pair function in `emissions/converters.py`:

- Is one Python function with a known transformation factor.
- Has a test in `emissions/tests/test_converters.py` with a known-good value.
- Goes through PR review before it can be used.
- Is enumerable. The dimension-crossing check (`test_no_dimension_crossings_registered`) walks the registry and fails if anyone adds a cross-dimension entry.

The cost is real. New units don't come for free. The benefit is that every conversion in the system is a deliberate, reviewed call. For audit data this is the right trade.

### What's there instead

A small registry in `emissions/converters.py`. Today: nine functions covering `kWh / MWh / GJ -> kWh`, `L / m3 -> L`, `kg / t / TO -> kg`, `km / mi -> km`. A new `(raw_unit -> canonical_unit)` pair is one function plus one test.

### What would come first if this expanded

A per-fuel density module so that mass-input-to-volume-canonical conversions become explicit per fuel rather than impossible. The shape would be a separate `emissions/density.py` with entries like `("DIESEL_B7", "L") -> 0.835 kg/L`. Conversion would dispatch by material code, not by abstract dimension. That stays explicit; it just adds another axis to the registry.

---

## What about the other things that aren't here

There are smaller gaps that didn't make this list because they aren't deliberate architecture decisions — they're scope cuts that would be obvious to add later:

- Reparse / replay of source records when a parser bug is fixed. The `REPARSED` audit action exists; the management command doesn't.
- Per-utility PDF templates beyond the one Con Edison-style layout.
- Cabin-class-aware air-travel factors (today the factor is short-haul-economy-style for every air segment).
- FX normalization for procurement spend and lodging amounts.

These would be in a v2 plan. They aren't in this document because they're not the same kind of decision as the three above. The three above would still be excluded with more time.
