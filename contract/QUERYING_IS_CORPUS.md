# How to query the IS corpus

**For:** every agent that searches the India standards corpus with `search_engineering_standards`:
- the HR Steel design agent (`steltic_india`);
- the CFS Steel design agent (`steltic_CFS_india`);
- the nonlinear Review agent (`steltic_nonlinear_india`, `snl review`).

The nonlinear Collect step makes the same kind of lookups itself (see section 9).

**Editions.** These rules are locked to the editions in the document table below. On any edition change, re-check every id format, trap and honest absence before reusing them.

**The corpus.** The corpus is the user's own. It is built in the Steltic hub from the BIS PDFs they licensed (IS corpus module: Convert, Rebuild index, Validate, Import fixed corpus). The search tool reaches it through `RAG_API_URL`. Nothing here is standard text: it is how to ask.

---

## 1. One call is one question

The call is synchronous: you send it and the answer comes back. There is no plan to submit and nothing to wait for.

| Field | Rule |
|---|---|
| `doc` | **One** canonical document stem (section 2). Never search every document blindly. |
| `type` | One of the following:<br>• `exact_section`: a clause id, e.g. `8.2.2`<br>• `exact_table`: a table, figure or section designation, e.g. `Table 4`, `Fig. 1`, `HB 300`<br>• `fts`: full text, used only to **navigate** to an id<br>`exact_equation` exists but finds almost nothing in BIS documents (section 5). |
| `query` | For an exact type: **the id alone**. For `fts`: the standard's own printed words, one idea. For a town: the town name alone. |
| `purpose` | Why you need it, in a few words. It goes into the provenance. On CFS it is also the IS 800 gate (section 3). |
| `context_neighbors` | 0 to 2. Use `1` when an expression needs its surrounding "where:" list. |
| `want_commentary` | Always `false`. BIS documents carry no separate commentary. |
| `chapter` | Optional. It narrows an `fts` query to one section of the standard, e.g. `8` or `12`. It is never a substitute for the id. |
| `collection`, `clause` | Legacy aliases of `doc` and of an exact id. Prefer `doc` + `type` + `query`. |

```
good:  {"type": "exact_section", "doc": "IS_800_2007", "query": "8.2.2.1", "purpose": "Mcr", "context_neighbors": 1}
good:  {"type": "exact_table",   "doc": "IS_1893_Part_1_2016", "query": "Table 3", "purpose": "zone factor Z"}
good:  {"type": "fts",           "doc": "IS_1893_Part_1_2016", "query": "Guwahati", "purpose": "seismic zone"}
bad:   {"query": "IS 800:2007 clause 8.2.2 lateral torsional buckling of laterally unsupported beams"}
```

The bad call looks like it works. The tool applies the policy to whatever arrives (section 7), but the call it can form from a sentence is a guess. The call you write yourself is not.

---

## 2. Documents

Send the stem in `doc`. The collection name is what the activity log and the report's grounding count use.

| Document | `doc` | Collection | What it governs |
|---|---|---|---|
| IS 800:2007 | `IS_800_2007` | `engineering_standards_IS800` | Hot-rolled members and connections, stability, Section 12 seismic |
| IS 18168:2023 | `IS_18168_2023` | `engineering_standards_IS18168` | Steel seismic design and detailing: Ry / Ru, the overstrength factor, zone restrictions |
| IS 1893 (Part 1):2016 + Amd 1, 2 | `IS_1893_Part_1_2016` | `engineering_standards_IS1893` | Seismic loads: zone, spectrum, R, I, drift, irregularity |
| IS 875 (Part 1):2026 | `IS_875_Part_1_2026` | `engineering_standards_IS875_P1` | Dead loads (unit weights) |
| IS 875 (Part 2):1987 | `IS_875_Part_2_1987` | `engineering_standards_IS875_P2` | Imposed loads |
| IS 875 (Part 3):2015 | `IS_875_Part_3_2015` | `engineering_standards_IS875_P3` | Wind |
| IS 875 (Part 4):1987 | `IS_875_Part_4_1987` | `engineering_standards_IS875_P4` | Snow |
| IS 875 (Part 5):1987 | `IS_875_Part_5_1987` | `engineering_standards_IS875_P5` | Special loads and load combinations |
| IS 2062 (Part 1):2025 | `IS_2062_Part_1_2025` | `engineering_standards_IS2062` | Steel grades: fy by thickness, fu |
| IS 808:2021 | `IS_808_2021` | `engineering_standards_IS808` | Hot-rolled section properties |
| IS 1161:2014 | `IS_1161_2014` | `engineering_standards_IS1161` | Tube properties |
| IS 816:1969 | `IS_816_1969` | `engineering_standards_IS816` | Welding |
| IS 9595:1996 | `IS_9595_1996` | `engineering_standards_IS9595` | Welding procedures |
| IS 4000:1992 | `IS_4000_1992` | `engineering_standards_IS4000` | HSFG bolts |
| IS 801:1975 | `IS_801_1975` | `engineering_standards_IS801` | Cold-formed members (CFS) |
| IS 811:1987 | `IS_811_1987` | `engineering_standards_IS811` | Cold-formed section properties (CFS) |
| IS 811:1987 Amd 1 (2011) | `IS_811_1987_Amd1_2011` | `engineering_standards_IS811_Amd1` | Substitutions only |

---

## 3. Routing: which document to ask

Choose in this order: **material → system → member → loading → method**, then ask the ONE document that governs.

| Agent | Ask | Do not ask |
|---|---|---|
| **HR Steel** | IS 800, IS 18168, IS 808 / IS 1161 / IS 2062, and IS 816 / IS 9595 / IS 4000 for connections | IS 801 / IS 811 (unless the job has CFS members) |
| **CFS Steel** | IS 801, IS 811 (+ Amd 1) | IS 800 / IS 18168, **except** for the hot-rolled lateral frame with an allow-listed `purpose` (`lateral_frame_is800`, `serviceability_limits_table6`, …). Without one the tool refuses (C6). Never use IS 800 for a cold-formed member capacity. |
| **NL Review** | IS 1893 (spectrum, drift, time history), IS 800 Section 12 (joint rotation, reference only), IS 18168 (Ry / Ru, capacity design), IS 2062 Table 3, IS 808 | Any foreign document |
| **All** | Loads, every job: IS 875 Parts 1–5 and IS 1893. Write each value into `cfg["load_plan"]` with its hit file and quote. | Any foreign standard: there is no foreign design basis (D3) |

---

## 4. Id formats

These were checked against the corpus.

```
IS_800_2007          section 8.2.2 · 8.2.2.1 · 7.1.2.1 · 9.3.2.2 · 12.8 · annex E-1.1
                     table Table 2 · Table 4 · Table 5 · Table 6 · Table 8(a) · Table 9(a)…9(d) · Table 13(a) · Table 13(b)
IS_1893_Part_1_2016  section 6.4.2 · 7.2.4 · 7.6.2 · 7.8.2 · 7.11.1.1 · 7.11.3
                     table Table 3 · Table 4 · Table 8 · Table 9 · Table 10
IS_875_Part_3_2015   section 6.3.2.2 · 6.3.3 · 6.3.4 · table Table 1 · Table 2 · Table 5 · Table 6 · figure Fig. 1
IS_875_Part_1_2026   table Table 1         IS_875_Part_2_1987  table Table 1 · Table 2
IS_875_Part_4_1987   section 5.2.1         IS_875_Part_5_1987  section 8.1
IS_18168_2023        section 1.3 · 5.2 · 5.5 · 8.2 · table Table 1 · Table 2
IS_2062_Part_1_2025  table Table 3 (mechanical properties)
IS_801_1975          section 6.1.2 · 6.5 · 6.6.1.1
IS_811_1987          table Table 1 … Table 11 (caption record) · a section by its engine label: CLR100X50X15X2
IS_808_2021          a section by designation: HB 300 · WPB 300 x 300 x 100.85
IS_1161_2014         a tube by size: 168.3x6.3
IS_816_1969          section 6.2.2      IS_4000_1992  section 4      IS_9595_1996  section 5
towns                fts with the town name alone, in IS_1893_Part_1_2016 (Annex E) or IS_875_Part_3_2015 (Annex A)
```

- **Tables.** `Table 4` and `4` both work. Keep a printed sub-letter: `Table 9(c)`, not `Table 9 c`.
- **Figures.** Figures are `exact_table` with `Fig. N`. `Fig. 1` does not match `Fig. 10`.

---

## 5. Traps

These are real. A "better" guessed id is always wrong.

- **IS 800 Tables 9, 13 and 8 are printed as sub-tables:**
  - Table 9(a) / 9(b) / 9(c) / 9(d) give fcd for buckling classes a, b, c and d;
  - Table 13(a) / 13(b) give fbd for αLT = 0.21 / 0.49;
  - Table 8(a) / 8(b) give χ.

  Ask for the sub-table you need. Asking for "Table 9" gets the first part only.
- **IS 800 Table 4 vs Table 5.** Table 4 is the partial safety factors for **loads** (γf, the load combinations). Table 5 is the partial safety factors for **materials** (γm0, γm1). Table 6 is the deflection limits.
- **IS 800 has almost no numbered equations.** `exact_equation` finds nothing. Ask for the clause (`exact_section 8.2.2.1`) with `context_neighbors: 1`.
- **IS 1893 (Part 1):2016 is amended.** Table 8 (I) and Table 9 (R) are printed "as amended by Amd 2, Nov 2020". Cite the amendment with the value. Table 10 is the percentage of imposed load in the seismic weight, not R.
- **Towns:**
  - Zone Z comes from IS 1893 Annex E and basic wind speed Vb from IS 875 (Part 3) Annex A. Send `fts` with the town name alone to **that** document; the same town name sent to IS 800 is answered "not listed".
  - A town in neither annex (Noida, for example) comes back `not_tabulated`. That is a definite answer. Read the zone or wind map (IS 875-3 `Fig. 1`) or use the EOR's site ruling. Do not re-word it.
- **IS 875 (Part 3):2015.** Table 5 is Cpe for **walls**; Table 6 is Cpe for **pitched roofs**. k2 is Table 2, k3 is 6.3.3, and k4 (cyclonic) is 6.3.4.
- **IS 875 (Part 5) combinations are 8.1.** There is no 8.1.1 record: ask for 8.1 with `context_neighbors: 1`.
- **IS 2062 (Part 1):2025.** fy and fu are in **Table 3** (Rm, and ReH by thickness band; the row is the same for every quality of a grade). Table 1 is chemical composition and Table 2 is product-analysis variation: no strengths.
- **Section properties.** Ask for the designation: IS 808 `HB 300`, IS 1161 `168.3x6.3`, IS 811 `CLR100X50X15X2`. Do not ask for "Table 1". That gives the table's caption record, not the row you need.
- **IS 811 Amd 1 (2011)** holds substitutions only. An empty answer for a property is honest (`found: false`).
- **A table hit's `section` may be the clause that cites the table.** The table's own id is in `table_id`, or in its caption as the `title`.
- **BIS documents have no commentary.** A note under a table is part of the table. A foreword never supplies a design value.
- **IS 1893 (Part 1):2016 gives no acceptance criteria for nonlinear analysis.** Nonlinear results are for information (D6/D7). There is nothing to find.

---

## 6. Ten rules

1. **One question per call, one document per call.** Several calls in a row are cheap. One vague call is not.
2. **Exact id when known.** If you don't know it: one `fts` in the standard's words, then the exact id in the next call. Never invent an id.
3. **Printed words, not chat.** Use "laterally unsupported beams", not "beam bends sideways". Use "equivalent static method", not "the simple method".
4. **Fetch everything an expression needs.** Every expression you compute from needs its "where:" variables (`context_neighbors: 1`), its applicability limits and its exceptions. Ask for each.
5. **Clause + table + limits beat "all of Section 8".** For example: `8.2.2` + `8.2.2.1` + `Table 13(a)`.
6. **Read what the corpus returns.** Read the ids it gives you and ask for them exactly. The wording that worked is the wording to use next time.
7. **`found: false` is an honest answer.** Narrow a query that was too broad, or ask for the parent clause. Do not fill the gap from memory without declaring it (rule 10).
8. **Cite from this session only.** Every number in a calculation comes from a verbatim excerpt returned this session. Cite the document, edition (and amendment), clause, table id and printed page. Put the saved `rag/` file in `hit_file`.
9. **Work in three waves:**
   1. navigation and the core provisions;
   2. definitions, limits and the cross-references the results name;
   3. a digit-by-digit check of every factor that entered a number you report.
10. **Designing from memory is a last resort, and it is declared.** In the report, state which value, which clause you believe it comes from, and that it was **not verified against the corpus**. Never invent a clause, table or factor.

---

## 7. What the tool does for you, and what comes back

**The policy, applied to every call:**
- A bare id typed into `query` is an exact lookup.
- A sentence naming ids is split: first one exact lookup per id, then ONE navigation query in the remaining words (ids removed).
- The result records the form that was sent in `policy`, e.g. `exact-id 8.2.2 · fts «laterally unsupported beams»`.
- A result in `exact_ids` with `exact_match: true` is final. It is the record you asked for, even if it is only one hit.

**The ladder, before anything is reported absent:**
1. the query as asked;
2. without the `clause` / `chapter` filter;
3. as an exact id lifted out of the words;
4. reworded through the corpus's synonym layer;
5. without the document filter.

If step 5 answers, the result says which document answered (`also_found_in`, or "FOUND ONLY WITHOUT THE DOCUMENT FILTER"). Cite **that** document, and check it governs.

**Labels on a result:**
- `thin`: the best answer was a single weak hit. Treat it as a lead, not an answer.
- `escalated`: a later rung answered. Use its wording next time.

**`not_found_kind`:**

| Kind | What it means | What to do |
|---|---|---|
| `no_specification_index` | No specification corpus on this PC. | Stop searching. Design from memory, **declared**. It says nothing about the standard. |
| `document_not_in_corpus` | That document was never converted here. The reply names the documents that are. | Ask one of those if it governs; otherwise cite from memory, declared. |
| `not_tabulated` | The corpus answered: the item has no table row (a town in neither annex). | Use the map or the EOR ruling. Do not re-word. |
| `server_error` | A retrieval failure (`found: null`). | Retry. **Never** report the provision as absent. |
| `term_absent_from_document` | The only kind that is a statement about the standard. | Re-word **once** in printed words, or ask for the parent clause, then accept it. |

**Transport failures.** If the configured corpus server cannot be reached, the run **pauses** (restart the IS corpus module, then Continue). If no corpus is configured at all, the tool says so once, and every clause is then cited from memory and declared.

---

## 8. One wave, as calls

```json
{"type": "exact_section", "doc": "IS_800_2007",         "query": "8.2.2",      "purpose": "LTB procedure", "context_neighbors": 1}
{"type": "exact_section", "doc": "IS_800_2007",         "query": "8.2.2.1",    "purpose": "Mcr expression and variables", "context_neighbors": 1}
{"type": "exact_table",   "doc": "IS_800_2007",         "query": "Table 13(a)", "purpose": "fbd, alpha_LT = 0.21"}
{"type": "exact_table",   "doc": "IS_800_2007",         "query": "Table 2",    "purpose": "section classification limits"}
{"type": "exact_table",   "doc": "IS_1893_Part_1_2016", "query": "Table 9",    "purpose": "R for the system (as amended)"}
{"type": "fts",           "doc": "IS_1893_Part_1_2016", "query": "Kolkata",    "purpose": "zone (Annex E)"}
{"type": "exact_table",   "doc": "IS_808_2021",         "query": "HB 300",     "purpose": "section properties"}
```

---

## 9. The nonlinear Collect step

`snl collect` does not let a model search.
- **The program fetches.** It knows which IS table or clause each value is read from (`plan_for`) and fetches it with the exact lookups this document describes:
  - IS 2062 `Table 3`;
  - IS 18168 `Table 1`;
  - IS 1893 `Table 3` / `Table 8` / `6.4.2` / `7.2.4`;
  - IS 800 Section 12 by system.
- **The row comes from the building.**
- **The transcriber only copies.** Whether it is the hub's model or an agent writing `collect_answers.json` from `collect_request.md`, it copies each value with a verbatim quote from the passages it was given. It must not search, and it must not use a value that is not in those passages.

A passage that does not contain the value is reported missing. It is never filled in from memory.
