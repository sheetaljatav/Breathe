# Sources

For each of the three source types, this document covers what was researched, what was learned, what the sample data models and why, and what would fail under real customer load.

---

## 1. SAP — fuel and procurement

### Research

SAP exposes operational data through several mechanisms, each with very different access requirements:

| Mechanism | What it is | Why analyst tools rarely consume it |
|---|---|---|
| **IDoc** | EDI-style XML or flat-file messages emitted by SAP for inter-system communication | Requires a listener (SAP PI/PO or a partner endpoint), per-customer IDoc message-type configuration, and an agreement with the customer's BASIS team on what to listen for. Months of setup per customer. |
| **BAPI / RFC** | Stored-procedure-style remote calls over RFC | Requires a named SAP user with authorization for the specific BAPI, plus an RFC connection (SAP GUI scripting, PyRFC). The customer has to provision and maintain it. |
| **OData (SAP Gateway)** | REST endpoints over SAP entity sets | Requires the customer to have SAP Gateway configured and OData services activated for the relevant entities. Often blocked by the customer's security team. |
| **SE16N / SQVI flat-file export** | An analyst opens SE16N or SQVI in SAP GUI, queries an MM or FI table, and uses "Save list as → File". Result: a CSV. | This is what actually shows up in an analyst's inbox. Human-mediated but trivially reproducible. |

SE16N CSV was the chosen format because it's what an analyst-facing tool actually receives in v1. Auto-pull from IDoc / BAPI / OData is a per-customer integration that this prototype deliberately doesn't ship (see `TRADEOFFS.md` #1).

### What was unexpected

- **German configuration is the realistic default.** Multinational corporations frequently run SAP in German-language mode regardless of where the analyst sits. Column headers come out as `Werk` (plant), `Buchungsdatum` (posting date), `Menge` (quantity), `BasisME` (base UoM), `Nettowert` (net value), `Waehrung` (currency). Decimal mark is comma, thousands separator is dot: `1.234,56`. Dates are `DD.MM.YYYY`.
- **Plant codes (`Werk`) mean nothing without a lookup.** `1000` is a 4-character string; the customer's facility-name mapping lives in a separate SAP table (`T001W`) that doesn't always come out with the data. Production ingestion needs a per-customer `PlantCode` lookup, populated during onboarding.
- **Material codes carry the activity-type signal.** Customers don't always export the material short text (`Materialkurztext`); the code prefix is what's reliable (`DIESEL_*`, `OFFICE_*`, `IT_*`). Production-grade would also pull from MARA (material master) but that's a separate extract.
- **The CSV file has a UTF-8 BOM.** SAP's GUI export adds `\xef\xbb\xbf` to the first line. Decoding with `utf-8-sig` handles it cleanly; plain `utf-8` decoding leaves the BOM glued to the first column header and breaks everything silently.
- **Metric tonne is `TO`, not `t` or `kg`.** Easy to miss when writing a unit converter that assumes ISO codes.

### Sample data

`samples/sap_se16n_export_2026Q1.csv` — 48 rows mixing fuel (most) and procurement, across the four Acme plants that `seed_demo` creates. Deliberate quirks the parser is expected to handle:

| Row | Quirk | Expected outcome |
|---|---|---|
| `ZZZZ;30.03.2026;DIESEL_B7;...` | Plant code not in lookup | `ParseError(UNMAPPED_PLANT)`. Row still gets a SourceRecord and a draft ActivityRecord with an empty `facility_code`. |
| `2000;15.03.2026;DIESEL_B7;...;220,00;GAL;...` | Unit `GAL` not registered (US-gallons data-entry mistake) | `ParseError(UNKNOWN_UNIT)`. No ActivityRecord. |
| `1000;33.03.2026;DIESEL_B7;...` | Day 33 (invalid date) | `ParseError(BAD_DATE)`. No ActivityRecord. |
| `1000;19.03.2026;DIESEL_B7;...;15.450,00;L` | Quantity roughly 10× the rolling median for the plant | Anomaly hint on the queue (rule-based, non-blocking). |

### What would break under real load

- **Multi-currency.** Procurement spend arrives in EUR or USD per plant. The prototype treats currency as a passthrough field. Production has to FX-normalize using a daily rate pinned at posting date, and that pinning needs the same audit treatment as factor pinning.
- **Material master enrichment.** The prefix heuristic (`DIESEL_*` → fuel) breaks for customers who use Z-codes (`ZMAT_001`). Production needs MARA, or a per-customer material-to-category mapping table populated during onboarding.
- **Multi-period postings (BUDAT vs. BLDAT).** SE16N exports include both posting and document dates. The current implementation uses posting date (`BUDAT`). Cross-fiscal-period audits would need both.
- **Header-name variation.** Different SAP configurations rename `BasisME` to `Basismengeneinheit`. The current parser hardcodes the short form. Production needs fuzzy header mapping.

---

## 2. Utility — electricity

### Research

Real ways a facilities team gets electricity data:

| Mechanism | Reality |
|---|---|
| **Portal CSV export** | The most common path. Commercial utilities (Con Edison, Duke, PG&E, EDF, EnBW, etc.) all expose a "download my usage" CSV in the commercial-customer portal. Schema varies per utility — typically `meter_id`, billing period, kWh, rate class, charges. |
| **Emailed PDF bill** | Universal. Every utility sends a monthly statement. Layouts vary widely. Most are text-extractable (generated by a billing system, not scanned). Some smaller cooperatives still send scanned PDFs. |
| **AMI / Green Button API** | Technically the cleanest. Green Button (ESPI) is a US standard for interval-meter data. Not every utility supports it; commercial accounts usually require per-utility opt-in. |
| **Direct utility API** | A few large utilities expose REST APIs (PG&E's SMD; others have partner APIs), each bespoke and rate-limited. |

Portal CSV is the primary path here; text-extractable PDF is the secondary path. Both feed the same downstream pipeline and produce identical `SourceRecord` shapes. Shipping only one would have left a half-product.

### What was unexpected

- **Billing periods don't align with calendar months.** A typical commercial cycle is "15th of month N to 14th of month N+1". A naive sum-by-month rollup will either double-count or miss. Production reporting needs explicit proration when the consumer wants calendar-month views.
- **Units inside a single file aren't always consistent.** Facilities teams sometimes download kWh for one meter and MWh for another (different rate classes). The portal export schema doesn't always coerce. `consumption_unit` is therefore per-row here.
- **Rate class encodes structure.** `LP-3` (large commercial time-of-use) implies peak / off-peak / demand splits. `GS-1` (general service) doesn't. The current implementation preserves `rate_class` on the raw payload but computes emissions only against the simple `consumption_kwh` total.
- **PDF layouts are utility-specific.** The bundled PDF parser is templated against one Con Edison-style layout. Production needs a template per utility, populated during onboarding — the same shape as the plant-code lookup.
- **Scanned bills exist but are rare for commercial.** Mostly rural cooperatives and older small accounts. Routing those to a manual-entry queue is a better product call than OCR-and-hope.

### Sample data

`samples/utility_portal_export_meter_xyz.csv` — 11 rows across two meters (Chicago and Atlanta) spanning calendar-misaligned billing periods. Two deliberate quirks:

| Row | Quirk | Expected outcome |
|---|---|---|
| `...2026-03-15,2026-04-14,1075000,kWh,...` | 12× the 90-day rolling median for the meter | Anomaly hint on the queue. |
| `...2026-04-01,2026-04-30,12.1,MWh,...` | Same meter as the kWh rows, but reported in MWh | Parser normalizes through the converter (12.1 MWh → 12,100 kWh). |

`samples/utility_bill_acme_facility_03_2026.pdf` — text-extractable PDF generated by `samples/_generate_utility_pdf.py` (run once, regenerable). Models a Con Edison commercial bill: account header, service address, meter ID, billing period, consumption table, charges. The pdfplumber-based parser extracts the five anchor fields by labeled regex.

### What would break under real load

- **Per-utility PDF templates.** One regex template covers the generator here. Production needs templates per utility, plus a first-time-seen workflow that asks the customer to confirm field mappings.
- **Time-of-use emission factors.** Peak-hour electricity in many US grids is dirtier than off-peak (gas peakers). The factor here is a flat per-grid-region average. Granular reporting needs hourly factors, which EPA and others publish via Cambium and WattTime.
- **Net metering.** Customers with on-site solar export back to the grid. Net consumption can be negative for some hours. The schema accepts signed Decimals, but no parser path subtracts for exports today.
- **Demand charges.** kVA demand signals load profile but doesn't change kWh-based emissions. The current implementation carries demand on the raw payload, ignores it in calculation, and lets the analyst sanity-check.

---

## 3. Corporate travel — Concur Reporting API v4

### Research

The SAP Concur Reporting v4 API (`/reportingapi/v4.0`) was the reference. The shape relevant for emissions:

```
/reports/{report_id}/expenses -> trips[] with segments[]
```

Each segment has a `type` field. In practice: `AIR`, `LODGING`, `CAR`, `RAIL` (rare in the US, common in EU), `MEAL`, `MISC`. Different segment types carry different fields:

- **AIR.** Vendor (airline code), origin / destination IATA codes, departure timestamp, distance_km (sometimes), cabin class, amount, currency. Distance is often missing — Concur stores what the booking system returned, and not every airline returns mileage.
- **LODGING.** Vendor (hotel brand), property_id, nights, check-in date, amount, currency.
- **CAR.** Vendor (Hertz, Uber, etc.), category (RIDESHARE / RENTAL_COMPACT / RENTAL_SUV / TAXI), distance_km when metered, amount, currency.

Navan, TripActions, and Egencia expose similar shapes — segment types and field names differ slightly but the model maps cleanly across them.

A JSON-paste endpoint accepting the documented response shape is the chosen transport, not OAuth + Reporting v4 integration. The reason is operational, not technical: Concur OAuth onboarding requires a corporate-customer relationship with SAP Concur and per-tenant App Center approval. The parser that ships here is exactly the parser a real integration would feed — only the transport changes.

### What was unexpected

- **`distance_km` is null more often than not.** Real Concur exports for many airlines just don't have it. Production handling needs an airport-pair distance fallback, which is shipped here using a seeded `Airport` table and great-circle math. An unknown airport pair becomes `UNRESOLVABLE_AIRPORT`, flagged for analyst review.
- **Cabin class matters a lot, and isn't always present.** Business-class long-haul flights carry roughly 3× the per-passenger emissions of economy. Concur captures `cabin_class` per segment but the field is optional in the API response. The current implementation uses a single short-haul-economy-style factor and flags this as a v2 follow-up.
- **Rideshare distances are metered; taxi distances often aren't.** When `distance_km` is null on a CAR segment, the implementation doesn't try to infer. It emits `MISSING_FIELD` and asks the analyst to enter the figure from the receipt.
- **Hotel emissions are inherently rougher than fuel or electricity.** Industry benchmarks (Cornell Hotel Sustainability Benchmarking) give per-room-night averages but with significant variance by climate, brand, and region. Production needs property-specific or brand-specific factors; v1 uses a single global per-night factor.

### Sample data

`samples/concur_reporting_v4_trip_response.json` — three trips, 12 total segments:

- **T-2026-001 (SFO ↔ ORD).** Explicit `distance_km` outbound, null on the return. Exercises the lookup fallback.
- **T-2026-002 (JFK ↔ LHR, business class).** Transatlantic with null distances. Forces lookup for both legs. Includes a deliberately invalid `LHR → XYZ` segment to exercise `UNRESOLVABLE_AIRPORT`.
- **T-2026-003 (FRA ↔ MUC).** Short-haul domestic. Exercises a German airport pair plus a rental-car segment with `distance_km`.

### What would break under real load

- **OAuth onboarding.** Each customer's Concur tenant needs OAuth scopes (`READ_REPORTS`, `READ_EXPENSES`) configured by their Concur admin. Refresh-token lifetime is six months. Production needs a refresh job and on-call coverage for expiry.
- **Pagination.** Reporting v4 returns at most 100 records per page. Real annual extracts span thousands of pages. Production needs a cursor loop with backoff (Concur rate-limits at 4 req/sec per tenant).
- **Segment-type drift.** Concur adds new segment types over time (electric scooter, e-bike rental in some markets). The enum-style dispatch here needs an "unknown type — defer to analyst" path; today it just emits `UNKNOWN_CATEGORY`.
- **Currency.** Lodging amounts arrive in local currency (GBP for London, EUR for Frankfurt). The current implementation preserves currency on the raw payload but doesn't FX-normalize. Spend-based travel factors (used as fallback when nights or distance are missing) require currency normalization.
- **PII.** Concur responses contain employee names, emails, sometimes home addresses. `SourceRecord.raw_payload` would persist these. Production needs a redaction pass before the JSONB lands.
