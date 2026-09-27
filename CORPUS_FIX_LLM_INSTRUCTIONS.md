# Fixing a first-pass India (BIS) standards corpus: instructions for an LLM agent

You are an LLM agent with code execution. A user has given you three things:

1. A zip of a **first-pass corpus**. The Steltic hub made it from the user's own licensed BIS PDFs: Docling conversion, index build, query server and validation.
2. A folder with those **licensed BIS PDFs**.
3. This file.

Fix the corpus, and give back a **replacement corpus zip** and a **FIX_REPORT.md**. The user drops the zip back into the hub. From then on, the Steltic design engines ground every code clause, table value and figure reading on it. A wrong number in the corpus becomes a wrong number in a structural design, so work like a checker, not a summariser.

The content is licensed. It is for this user only (see section 8).

Contents:

1. Inputs and outputs
2. Documents, stems, editions, collections
3. What the engines need from the corpus
4. Corpus format: how to write each kind of fix
5. Build and validate commands
6. Procedure, steps 1 to 12
7. Known defects checklist
8. Rules
9. Acceptance and FIX_REPORT.md

---

## 1. Inputs and outputs

### 1.1 Inputs

- `corpus.zip`: the first-pass corpus. Unzip it into a work folder; call it `<corpus>` below. Its root should hold `documents/`, `indexes/` and `search/`. It may also hold `scripts/` (the hub's bundled corpus scripts), `cache/`, `queue/` and `INDIA_MANIFEST.json`.
- The PDF folder. File names are arbitrary. Identify each PDF by its title page (step 1).
- This file.

Work in three folders: `<corpus>`, `<pdfs>` (copies or symlinks of the PDFs, renamed `<STEM>.pdf`) and `<scratch>` (page renders, crops, OCR output, traces). **Nothing from `<pdfs>` or `<scratch>` goes into the output.**

If the zip has no `scripts/` folder, ask the user for the hub workspace's `scripts/` folder. It is the corpus module's code: `build_index.py`, `validate.py`, `retrieval.py`, `corpus_fixes.py` and so on. If you cannot get it, do every content fix in section 4, skip steps 10 and 11, check the probes in 6.11 by hand, and tell the user in FIX_REPORT.md to run **Rebuild index** and then **Validate corpus** in the hub.

### 1.2 Output: `corpus_fixed.zip`

The zip must have exactly this layout at its root. Paths are relative; there is no enclosing folder.

```
documents/standards/<STEM>/                    one folder per stem (section 2)
    markdown/<STEM>.search.md                  the SERVED text, all pages, with page markers (4.1)
    markdown/pages_search/page_NNN.md          one file per page, same text as the matching segment
    markdown/<STEM>.md, pages/, pages_recovered/, chunks/, furniture/, <STEM>.furniture.md
                                               conversion output: keep, watermark-stripped
    tables/*_pNNN_*.{md,csv,json}              converted grids (keep; superseded ones stay for audit)
    tables/<STEM>_Table_<N>_recovered.{md,csv} hand transcriptions (4.3)
    tables/<STEM>_Fig_<N>_recovered.{md,csv}   figure transcriptions (4.7)
    tables/recovered_index.json                index of every transcription (4.3, 4.7)
    structured/sections.csv, sections_check.json   IS 808 / IS 811 / IS 1161 only (4.5)
    structured/table1_unit_weights.csv         IS 875-1 only (4.6)
    structured/{<STEM>.json, blocks.jsonl, page_map.json, furniture_by_page.json, chunks/}  conversion output
    indexes/{documents,sections,equations,tables}.json   per-document indexes (rebuilt)
    equations/, convert_meta.json, postprocess_meta.json, validate_report.json   (keep)
indexes/{documents,sections,equations,tables,aliases,us_terms_not_in_IS,master_toc,build_stats,validate_corpus}.json
indexes/master_toc.md
search/spec_fts.sqlite                         FTS5 index, rebuilt by build_index.py
INDIA_MANIFEST.json                            rebuilt by the build
scripts/quality.json, scripts/bis_manual_sections.json, scripts/is811_manual.json
                                               ONLY the ones you changed; data files, never .py (4.10)
FIX_REPORT.md                                  section 9
```

Leave out of the zip:

- PDFs, page images, crops and overlays;
- `cache/` (the query cache is rebuilt, and a stale one is discarded anyway) and `queue/`;
- `__pycache__/`;
- backup files (`*.bak*`, for example `*.search.md.bak_ocr_*`);
- any modified `.py` file.

If a code change is needed (for example a new alias group or a new retrieval rule), describe it in FIX_REPORT.md under "Proposed code changes" and do not ship it. The hub copies its own `scripts/*.py` over the workspace's, so shipped code would be lost anyway.

---

## 2. Documents, stems, editions, collections

The stems are fixed. The engines, the hub's server and every index key on them. **Never rename a stem**, even when the name looks wrong.

| stem | edition field (exact) | collection (engines) | family | notes |
|---|---|---|---|---|
| `IS_800_2007` | `2007` | `engineering_standards_IS800` | hr | General construction in steel |
| `IS_801_1975` | `1975` | `engineering_standards_IS801` | cfs | Cold-formed; scanned print; Amd 1, reaffirmed 2010 |
| `IS_808_2021` | `2021` | `engineering_standards_IS808` | hr | Hot-rolled section properties |
| `IS_811_1987` | `1987` | `engineering_standards_IS811` | cfs | Cold-formed section properties; scanned |
| `IS_811_1987_Amd1_2011` | `2011` | `engineering_standards_IS811_Amd1` | cfs | One-page Amendment No. 1 (Nov 2011) |
| `IS_816_1969` | `1969` | `engineering_standards_IS816` | hr | Welding (metal arc); scanned |
| `IS_1161_2014` | `2014` | `engineering_standards_IS1161` | hr | Steel tubes (CHS only) |
| `IS_1893_Part_1_2016` | `2016+A1+A2` | `engineering_standards_IS1893` | hr | Amd 1 (Sep 2017) and Amd 2 (Nov 2020) consolidated into this stem |
| `IS_2062_Part_1_2025` | `2025` | `engineering_standards_IS2062` | hr | Structural steel |
| `IS_4000_1992` | `1992` | `engineering_standards_IS4000` | hr | HSFG bolts |
| `IS_875_Part_1_2026` | `2026` | `engineering_standards_IS875_P1` | hr | Dead loads. Confirm the year on the title page (see below) |
| `IS_875_Part_2_1987` | `1987` | `engineering_standards_IS875_P2` | hr | Imposed loads; Amd 1 (Dec 2006), reaffirmed 2013 |
| `IS_875_Part_3_2015` | `2015` | `engineering_standards_IS875_P3` | hr | Wind loads |
| `IS_875_Part_4_1987` | `2021` | `engineering_standards_IS875_P4` | hr | **Holds IS 875 (Part 4):2021.** The stem name is historical and stays |
| `IS_875_Part_5_1987` | `1987` | `engineering_standards_IS875_P5` | hr | Load combinations; scanned |
| `IS_9595_1996` | `1996` | `engineering_standards_IS9595` | hr | Welding recommendations |
| `IS_18168_2023` | `2023` | `engineering_standards_IS18168` | hr | Earthquake-resistant steel buildings |

- **Collection spellings.** The server also accepts the prefix `engineering_standard_`, the short keys (`IS875_P3`, `IS1893_P1`, `IS811_AMD1` …) and the stems themselves. The mandatory load collections of every design job are `IS875_P1` to `IS875_P5` and `IS1893`.
- **Stem alias.** `IS_875_Part_4_2021` resolves to `IS_875_Part_4_1987`. Its `documents.json` must say edition `2021` and standard `IS 875 (Part 4):2021`, and its title must not contain "1987".
- **IS 875 (Part 1).** The reference build read 2026 from the title page. Read your copy's title page. If it prints another year, keep the stem, set `edition` to the printed year, and flag it in FIX_REPORT.md.
- **IS 1893.** The amendments may come inside the PDF (the reference copy carried them as sheets at the end) or as separate PDFs. Either way they belong to the one stem `IS_1893_Part_1_2016` (4.4).
  - Without both amendment sheets, set the edition to what you actually consolidated (`2016`, or `2016+A1`).
  - Say so prominently in FIX_REPORT.md. The engines are built on the consolidated A1 + A2 text, and the edition probe will fail.
- **A PDF of a different edition** (for example an IS 875 (Part 4):1987 print): keep the stem, record the true edition, do not apply the edition-specific fixes of section 7, and flag it in FIX_REPORT.md.

**When the user lacks a PDF:**

- Stem in the zip but no PDF: do only the fixes that need no PDF, namely the watermark, metadata, the file format and the build. Change no standard text. Set its quality in `scripts/quality.json` and `documents.json` to what you can vouch for (at most `UNREVIEWED`), and list it in FIX_REPORT.md.
- Stem absent from the zip: do not create it. The engines will receive "`<stem>` is not in the corpus" (`not_found_kind: document_not_in_corpus`), which is honest. The validate probes for that stem will fail: list them as "expected failures: document not supplied".
- Never add a stem for a document the user did not supply, such as IS 456, IS 1367 or IS 11384. Never copy text from another source into a stem.

**Page numbers.** Every page number in this file is the **pdf page of the reference licensed copies** ("ref p."). Your copy may be offset, for example by a store cover page. Find each item by its caption or clause id. Record the offset for each stem in FIX_REPORT.md.

---

## 3. What the engines need from the corpus

The engines call `search_engineering_standards`. It sends `POST /query` to the corpus server with:

```json
{"query": "...", "collection": "engineering_standards_IS1893", "top_k": 5,
 "clause": "7.6.4", "stem": "IS_1893_Part_1_2016", "doc": "IS_1893_Part_1_2016",
 "type": "exact_section|exact_table|exact_equation|fts|keyword|auto", "want_commentary": false,
 "context_neighbors": 0}
```

The reply is `{results:[{text, source, section, title, page, id, part, authoritative, score}], matched, note, count}`. The corpus library behind it (`retrieval.Corpus.search`) returns `{found, hits, note, not_tabulated, us_term, type}`; each hit carries `doc`, `edition`, `section_id`, `table_id`, `eq_id`, `pdf_page`, `printed_label`, `title`, `text` and `snippet`.

**How the engine reads a reply, and what that requires of the corpus:**

1. **Exact ids are final.**
   - A `clause` becomes an exact lookup: equation, then section, then table. A `"Fig. N"` / `"Figure N"` clause goes to `exact_table`.
   - If `matched` starts with `exact_`, the engine sets `exact_match: true` and stops searching.
   - So every clause, table and figure id the engines cite must resolve to **the right single record** with **clean text**. A garbled grid served on an exact hit becomes a design value.
   - Exact lookups must never cross-match: `Fig. 1` must not return `Fig. 10`, and `Table 7` must return its caption page, not a page that only mentions it.
2. **`not_found_kind`.** The engine sorts every miss into one of these kinds, and each has its own consequence:
   - `no_specification_index`: `search/spec_fts.sqlite` is missing; the job falls back to memory mode.
   - `document_not_in_corpus`: the stem is absent (note "`<stem>` is not in the corpus").
   - `not_tabulated`: a town is in neither IS 875-3 Annex A nor IS 1893 Annex E; the corpus note names the map to read.
   - `server_error`; and `term_absent_from_document`: the corpus holds the document but not the text, so the engine treats the provision as absent.

   So a missing clause heading, an OCR-garbled term or a lost table is not cosmetic. It makes the engine conclude that a provision does not exist.

   Keep the honest misses honest:
   - A town absent from both annexes must stay `not_tabulated`. Do not create text that looks like an annex town table (4.7).
   - US terms (SDS, Cd, Ω0, RBS, BRBF …) must stay `found:false` with the IS equivalent (`indexes/us_terms_not_in_IS.json`).
3. **`hit_file` quotes.**
   - The engine saves each hit's text to `rag/<file>.txt`.
   - Every retrieved value in a design must carry `{hit_file, quote}`, where the quote is found **verbatim** in that saved text, after whitespace is collapsed and case is folded.
   - So served text must be **verbatim standard text**, in reading order: no columns interleaved, no words split by line-break hyphens or markup, NFKC-clean Unicode (plain ε, not math-italic 𝜀), every number exactly as printed. Anything that is not standard text must be labelled as such (4.2).
4. **Provenance on every hit.** `pdf_page` and `printed_label` come from the page markers. A wrong marker makes every citation from that page wrong.
5. **Structured keys.** The engines look up section rows by designation (`exact_table "HB 300" --doc IS_808_2021`), CHS size (`168.3x6.3`) and IS 811 engine label (`CLR100X50X15X2`). They rely on `structured/sections.csv` (4.5).
6. **Town and map lookups.**
   - A wind or seismic town query is answered from the Annex A / Annex E pages. They are found by their printed titles "Basic Wind Speed at 10 m Height for Some Important Cities/Towns" and "Zone Factors for Some Important Towns".
   - A snow query containing a town is answered from the IS 875-4 `Fig. 1` figure record (4.7).
7. **The alias layer.** `indexes/aliases.json` is generated by the build from code, holds India terms only, and the engines reword queries with it. A conflict rule makes response-reduction-factor queries answer IS 1893 Table 9 first and flag IS 800 Table 23.

---

## 4. Corpus format: how to write each kind of fix

Everything below is consumed by the scripts named. If you write it in another shape, the build silently ignores it. After any change, rebuild (section 5) and query the item.

### 4.1 Served page text (`markdown/<STEM>.search.md` and `markdown/pages_search/page_NNN.md`)

- `<STEM>.search.md` is one file. Each page starts with a marker line:
  `<!-- pdf_page=N printed_label=L printed_label_qualified=Q part=standard -->`.
  - `L` is the folio printed on the page. Use `None` when the page has none, for example a cover, which must never carry a year.
  - `part` is always `standard` for BIS documents.
- `pages_search/page_NNN.md` (three digits) must hold the same text as that page's segment. **The build keeps whichever of the two is longer** (`build_index.parse_pages`), so if you fix only one file the other can silently win. **Edit both, identically.**
- HTML comments (`<!-- … -->`) are stripped before indexing. Use them for audit trails. Inside a comment, write `- -` instead of `--`.
- **Headings.** Clause headings must start a line, as `x.y.z Title`, `**x.y.z Title** — text` or `## x.y Title`. Annex ids start a line as `ANNEX D`, `D-1`, `E-1.1`.
  - The heading parser (`bis_text.parse_bis_headings`) reads the PDF text layer and the served text.
  - A heading that neither of them shows cleanly goes into `scripts/bis_manual_sections.json` (4.9).
- **Table captions.** A plain line starting `Table N` / `TABLE N` / `Table N(a)`, followed within about 6 lines by `(Clause …)` (or a `Sl No` / `(1) (2)` header row, or a Title-Case title).
  - A line starting with `**` does **not** match (`bis_text.CAPTION_RE`).
  - A table record exists only where a caption is detected on that page, in the PDF text layer or the served text. If both have lost it, restore the printed caption verbatim as a plain line above the table.
- **Reading order.** Linearise two-column pages (left column, then right). Remove running headers and footers, page furniture and conversion junk such as CID glyph codes (`G6B G6F …`, `(cid:NN)`, `/gidNN`). Move removed junk into a `<!-- SUPERSEDED TEXT (…; kept for audit): … -->` comment rather than deleting it silently. Keep `<!-- image -->` placeholders.

### 4.2 Labelled non-standard text

Anything in served text that is not standard text carries one of these labels (plus `TODO(verify, pdf p. N)` markers and the block markers of 4.3, 4.4 and 4.7):

- `[sic]`: the print itself carries a misprint (you checked the page image).
- `[sic?]`: the served text contradicts itself and you could not settle print against conversion. Use it rarely; prefer `TODO(verify, pdf p. N)`.
- **Transcriber notes**: `[transcriber note, not standard text: …]` inline, or a section headed `Reading notes (transcriber, not standard text)`.
- **Canonical line**, for a formula whose converted form is broken. Put it right after the broken formula, in both served files:
  `Canonical line [x.y restated from the licensed PDF p. N (printed p. L), <date>; verify]: <formula as printed, in plain Unicode>`.
  - Keep the broken original. It is standard text in a damaged form, and the canonical line sits beside it.
  - Several related formulas: `Canonical lines [...]: …`.

### 4.3 Table transcriptions (the "K02" pattern)

Use this for any table whose converted grid is wrong, scrambled or incomplete.

1. **Transcription file.** Write `tables/<STEM>_Table_<N>_recovered.md`.
   - Line 1: `<!-- transcribed from the licensed PDF p. P (printed p. L) by <method>, <date>; <what was hard> -->`.
   - Then the bold caption `**Table N <Title as printed>** (*Clause* x.y)`.
   - Then a Markdown table with every row, column header and note **as printed**: units in the header, notes below the table.
   - Uncertain cells: `TODO(verify, pdf p. P)` in the cell and a `[transcriber note, not standard text: …]`.
   - Beside it, `…_recovered.csv`: the same rows, one header row, UTF-8.
2. **Index entry.** Add an entry to `tables/recovered_index.json`. The file is `{"doc": "<STEM>", "updated": "<date>", "tables": [ … ]}`:
   ```json
   {"table_id": "N", "pdf_page": P, "md": "tables/<STEM>_Table_N_recovered.md",
    "csv": "tables/<STEM>_Table_N_recovered.csv", "title": "Table N <Title>", "section_id": "x.y",
    "method": "manual_transcription_<date>", "provenance": "manual_transcription",
    "num_rows": R, "num_cols": C}
   ```
   - `table_id` + `pdf_page` must equal a caption-verified table record of that page. Otherwise nothing attaches, so check `indexes/tables.json` after the build.
   - `table_id` forms: `"2"`, `"9(a)"`, `"26(b)"`, `"5"`.
   - A table running over several pages gets **one entry per page**, each pointing at that page's part (or at the whole transcription).
   - A non-caption table inside a clause uses an id like `"6.3.4-k4"` or `"6.4.2-Sa/g"`. Such entries are served only where a record with that id exists, so prefer a real caption.
3. **Served page.** In **both** served files, on that page:
   ```
   <!-- CORPUS-K02:p<P>-T<N>:start -->
   ...the transcription (same text as the .md, header comment optional)...
   <!-- CORPUS-K02:p<P>-T<N>:end -->
   <!-- SUPERSEDED TEXT (converted text, replaced by the transcription above; kept for audit):
   ...the old grid, with every "--" written "- -"...
   -->
   ```
   Keep the plain caption line (4.1) outside the comment.
4. **Effect at build time.** `corpus_fixes.apply_recovered_tables` replaces the grid in the table record, its title and its FTS row with the transcription. The old grid is no longer served on any path.

### 4.4 Amendment consolidation (IS 1893, and any other amended stem)

Put the amended clause text on the base page it amends, in both served files:

```
<!-- CORPUS-A:amd-<clause-or-table>:start -->
[This page carries clauses amended by Amendment No. 1 (<month year>) / Amendment No. 2 (<month year>). The consolidated (amended) clause text is given in the block below; where it differs, it supersedes the base text on this page.]
**7.6.4 …** [Amd 2, <month year>: clause substituted] <amended text verbatim>
<!-- CORPUS-A:amd-<clause-or-table>:end -->
```

- Mark every changed row or paragraph of an amended table, for example `[Amd 2, <month year> — row substituted]`.
- Deletions ("Fig. 4A middle figure — Delete") and caption substitutions get a transcriber note at the affected caption.
- Keep the amendment sheets as their own pages. List those pages in `documents.json` as `amendment_pages`: they are ranked below the consolidated text.
- An amendment clause id must resolve to the consolidated base page, not to the sheet.

### 4.5 Section-property tables (`structured/sections.csv`, `structured/sections_check.json`)

These apply to IS 808, IS 811 and IS 1161. One CSV row per designation, in SI units (mm, mm², mm⁴, mm⁶, kg/m). The columns (header row, in order):

- **IS 808:** `designation,table_id,table,type,pdf_page,mass_kg_m,A_mm2,D,B,tw,tf,flange_slope_deg,R1,R2,Cy,Cz,Ixx_mm4,Iyy_mm4,rxx,ryy,Zex,Zey,Zpx,Zpy,It,Iw,alpha_rad,Iuu_mm4,Ivv_mm4,ruu,rvv,units,check,repairs`
- **IS 1161:** `designation,table_id,NB,D,t,mass_kg_m,A_mm2,I_mm4,Z_mm3,r_mm,pdf_page,units,check,repairs`
- **IS 811:** `designation,table_id,table,type,pdf_page,h,b,c,t,Ri,mass_kg_m,A_mm2,Cx,Cy,Ixx_mm4,Iyy_mm4,Iuu_mm4,Ivv_mm4,Ixy_mm4,rxx,ryy,ruu,rvv,tan_alpha,Zx,Zy,Zu,Zv,x0,J_mm4,Cw_mm6,units,check,sources,repairs,label`

The rules:

- `designation` as printed, for example `HB 300`, `WPB 280 X 280 X 284.13`, `100 x 50 x 15 x 2.00`, `168.3x6.3`. `table_id` is the lookup key, usually the designation.
- IS 811 `label` = table prefix + dimensions joined by `X`, trailing zeros dropped. Prefixes by table: 1 `EA`, 2 `UA`, 3 `CWS`, 4 `CWR`, 5 `CLS`, 6 `CLR`, 7 `HS`, 8 `HRH`, 9 `HRB`, 10 `LZ`. Example: Table 6 `100 x 50 x 15 x 2.00` gives `CLR100X50X15X2`. `corpus_fixes.apply_section_checks` writes the labels.
- `check` is one of:
  - `PASS`;
  - `PASS (corrected from PDF p.P, <date>)`;
  - `FAIL: <reason>` / `FLAG: <reason>`;
  - `QUARANTINED: <reason>`.
- `repairs` records every cell changed by a documented rule.
- `sections_check.json`: `{stem, rows, pass, fail, repaired_rows, unresolved:[{designation, pdf_page, check}], quarantined:[…], source, plate_area_check}`.
- **Generation.**
  - Generate with `python scripts/build_section_tables.py --pdf-dir <pdfs>`. It needs `pdftotext`/`pdfinfo` and, for IS 811, `pdftoppm` + `tesseract`, and it runs `apply_section_checks`. Then correct single rows by hand (step 6.6).
  - **The structured records reach the index only through a with-PDF build** (5.2). `refresh_structured_rows` in a `--no-repair` build only refreshes records that already exist.
- `scripts/is811_manual.json` holds IS 811 cells that you read from the page image because both OCR sources failed:
  `{"_note": "...", "rename": {"<table>|<designation as OCR read it>": {"designation": "<true>", ...}}, "cells": {"<table>|<designation>": {"<col>": value, ...}}}`.
  - Values are in the **printed** units (cm, cm², cm⁴, cm⁶, kg/m).
  - `"_misprint": true` marks a printed value that is inconsistent with the rest of its row: it is kept as printed and flagged.
  - If the hub did not ship this file, create it.

### 4.6 IS 875 (Part 1) Table 1 rows (`structured/table1_unit_weights.csv`)

- `python scripts/build_is875_1_table1.py` reads the **served** Table 1 grid (from its caption to the Table 2 caption) and writes one row per material. Columns: `row, sl_no, group, sub_heading, material, nominal_size, weight_kN, unit, per, pdf_page, note`.
- So fix the served Table 1 first:
  - collapse cells the converter duplicated across columns;
  - restore the sub-heading hierarchy (indentation lost);
  - make each weight cell a number or range exactly as printed.
- Then run the script. The build turns each row into its own record (`corpus_fixes.table1_records`).

### 4.7 Figure transcriptions (the "K07" pattern)

Use this for graphs, maps and coefficient sketches whose values exist only as an image.

1. **Transcription file.** Write `tables/<STEM>_Fig_<N>_recovered.md`, plus a `.csv` for tabular data. In order:
   - Header comment: source page, date, method.
   - Bold caption `**Fig. N <Caption as printed>** (*Clause* x.y) — figure transcription: <the natural search words, e.g. "across wind force spectrum coefficient Cfs">`.
   - Provenance line (rule 8.3).
   - The table(s) of values.
   - `Reading notes (transcriber, not standard text)`: method, calibration, uncertainty, cross-checks and any erratum or amendment applied.
2. **Index entry.** Add a `recovered_index.json` entry:
   ```json
   {"table_id": "Fig. N", "kind": "figure_transcription", "figure_kind": "graph|map (zones + town table)|printed values|contour chart",
    "pdf_page": P, "printed_page": "L", "public_copy_pdf_page": null,
    "md": "tables/<STEM>_Fig_N_recovered.md", "csv": "tables/<STEM>_Fig_N_recovered.csv",
    "num_rows": R, "num_cols": C,
    "title": "Fig. N <caption> — <search words>, Figure N, clause x.y [figure transcription]",
    "section_id": "x.y", "uncertainty": "±… in …", "method": "figure_digitisation_300dpi_<date>",
    "provenance": "figure transcription from the licensed copy; graph/map reading, verify: True",
    "anchor": "^FIG\\. N <first words of the caption line on the served page>",
    "after_image": true, "supersede": ["<regex of junk lines from the figure image>"]}
   ```
   - The `table_id` of a coefficient sketch that belongs to a clause, not a numbered figure, is `"<clause>-shape"`, for example `5.2.1-shape`.
3. Run `python scripts/serve_figure_transcriptions.py`. Every line must print `OK`; `MISS` means the anchor regex did not match the caption line of that served page.
   - The script inserts the block `<!-- CORPUS-K07:<STEM>:<id>:start/end -->` after the caption, or after the following `<!-- image -->` when `after_image` is set.
   - It moves `supersede` matches into a SUPERSEDED comment.
   - It is idempotent.
   - Then rebuild. `corpus_fixes.figure_records` creates a table record (`figure_transcription: true`, `verify: true`).
4. **Town tables** inside figure records (IS 875-3 Fig. 1, IS 875-4 Fig. 1, IS 1893 Fig. 1):
   - One Markdown row per town. **The town name is the first cell** (`| Srinagar | …`); an alternate name may follow in brackets (`| Kochi (Cochin) | …`).
   - For the IS 875-3 wind reading, keep the column order `| Town (not in Annex A) | Map evidence | Vb (m/s) | Note |`. The server builds its not_tabulated note from cells 1 to 4.
   - IS 875-4 Fig. 1 must include one bullet line containing the phrase `outside the mapped area` that names the major non-snow cities the engines query (Chandigarh, Delhi, Noida, Kolkata, Mumbai, Chennai, …). A snow query for those towns returns that line.
   - **Never** put the annex titles ("…for Some Important Cities/Towns", "Zone Factors for Some Important Towns") into a figure record. They flag the page as an annex town table, and towns absent from the annex would then stop answering `not_tabulated`.
5. Two figures on one page (IS 875-3 Figs 14 and 15) get two entries with the same `pdf_page`. Full-text answers collapse hits by (doc, page), but `exact_table` returns each.

### 4.8 Aliases

- `indexes/aliases.json` and `scripts/aliases.json` are **regenerated by every build** from the code (`build_index.SEED_GROUPS` + `bis_text.CITY_GROUPS`). Do not hand-edit them.
- Check after the build:
  - no US groups (SDS, S_DS, Cd, Steel02, forceBeamColumn);
  - the partial-safety-factor groups kept apart (γm0, γm1 and γf are distinct);
  - the response-reduction conflict rule present;
  - the city variants cover the spellings your Annex A / Annex E print (Bengaluru/Bangalore, Visakhapatnam/Vishakhapatnam/Vizag, Kochi/Cochin, Gurugram/Gurgaon, Thiruvananthapuram/Trivandrum, Mumbai/Bombay, Chennai/Madras, Kolkata/Calcutta, Pune/Poona …).
- A missing group or variant is a **proposed code change** in FIX_REPORT.md. Never alter printed text to fit an alias.

### 4.9 Manual section headings (`scripts/bis_manual_sections.json`)

For clause headings that the PDF text layer and the served text both show garbled:

```json
{"_note": "...", "<STEM>": [{"section_id": "6.1", "title": "<title as printed>", "pdf_page": 12, "line": 3,
  "source": "manual (PDF image p12: text layer reads '<garbled form>')"}]}
```

- It takes effect **only in a with-PDF build** (`postprocess.repair_bis_doc_indexes`).
- In a PDF-less build, annex ids and amendment-sheet clause ids ("(Page 5, clause 8.5) — Substitute …") are picked up from the served text by `corpus_fixes.annex_sections` / `amendment_sections`.
- The better fix is to repair the heading line in the served text as well (4.1).

### 4.10 Metadata, quality, editions

**Per stem, `documents/standards/<STEM>/indexes/documents.json`** is a list with one record. Its fields: `id` (= stem), `edition`, `edition_title_page`, `title`, `standard`, `collection_name`, `family` (`hr`|`cfs`), `jurisdiction: "india"`, `amendments` (list), `amendment_pages` (list of pdf pages), `reaffirmed`, `supersedes`, `stem_alias`, `stem_note`, `image_only` (list of strings), `quality`, `known_defects`, `source_pdf`, `searchable_markdown` (`documents/standards/<STEM>/markdown/<STEM>.search.md`) and `pdf_pages_total`.

A with-PDF build rewrites this record:

- `update_metadata.update_docs` takes the edition from the title page;
- the code dict `update_metadata.OVERRIDES` then overrides the edition, title, standard and amendment fields for IS 1893, IS 811 Amd 1, IS 875-4, IS 801, IS 875-2, IS 2062 and IS 18168;
- `scripts/quality.json` supplies `quality` and `known_defects`.

What to do about it:

- **After the with-PDF build, re-check every `documents.json`** against its title page.
- If an OVERRIDES value is wrong for the user's copy (for example `amendment_pages`, fixed to ref pp. 49–56 of IS 1893):
  1. correct it in `documents.json`;
  2. rebuild with `--no-repair`;
  3. propose the OVERRIDES change in FIX_REPORT.md.
- **`scripts/quality.json`** is `{"_note": …, "<STEM>": {"quality": "PASS|REPAIRED|DEGRADED|UNREVIEWED", "known_defects": ["…"]}}`. The build copies it into `documents.json` on every build, so update it, ship it, and mirror the same values in each `documents.json`.
  - `PASS`: verified, no known defect that affects a value.
  - `REPAIRED`: defects fixed, some prose OCR remains.
  - `DEGRADED`: values may be wrong outside the listed repairs.
  - `UNREVIEWED`: not checked.
- **`source_pdf`.** Point it at your local `<pdfs>/<STEM>.pdf` while you work. **Before packaging, set it to `null`**: a local path is useless to the user and may reveal your environment.

### 4.11 Watermark (owner decision D11)

- Licensed BIS PDFs carry a licensee line on every page: the sentence "Free Standard provided by BIS via BSB Edge Private Limited to <licensee> - <user>(<e-mail>) <IPv4>", or its "amendment" variant. Expect fragments of it glued onto standard text by the converter, and OCR-damaged variants on scanned prints ("BlS", "BSB Edqe" …).
- **No licensee name, user id, e-mail address or IP may remain anywhere** in `documents/`, `indexes/` or `search/`: in text, JSON, CSV, chunk files, table file names or FTS rows.
- BIS institutional addresses (`@bis.gov.in`, `@bis.org.in`, `@standardsbis.in`, the BIS office `vsnl.com` address) printed on back covers are allowed.
- Tools: `python scripts/strip_watermark.py --apply --paths documents indexes` rewrites files (JSON stays valid), and `--check` exits 1 if anything remains. Validate greps with `bis_text.has_watermark`, which fails on **any** non-BIS e-mail, so never write any e-mail address, including the user's, into the corpus.
- The FTS index is rebuilt from clean text by the build.
- **Also grep yourself** for the licensee's name and user id (read them from the PDF's watermark line) and for the IP. The regexes do not know the name.

---

## 5. Build and validate commands

Run everything from `<corpus>` with the corpus's own scripts. Set `export INDIA_CORPUS_ROOT=<corpus>` and `export QFM_NO_CACHE=1`.

### 5.1 Tools

- **Required:** Python 3.11+ and poppler (`pdftotext`, `pdftoppm`, `pdfinfo`, `pdffonts`).
- **Scanned pages:** `tesseract` 5 with the `eng` data.
- **Figures:** Pillow and numpy; scipy is optional.

Install what is missing (`pip install pdfplumber pymupdf pillow numpy`; `apt-get install poppler-utils tesseract-ocr`). You do not need Docling unless you re-convert a document.

### 5.2 With-PDF build (the main path)

Your PDFs are available, so use it. It re-derives clause headings, table captions, equations and structured rows from the PDF text layer and the served text.

```bash
# 0. each stem's documents.json: set "source_pdf" to "<pdfs>/<STEM>.pdf"
python scripts/strip_watermark.py --apply --paths documents indexes
python scripts/strip_watermark.py --check
python scripts/build_section_tables.py --pdf-dir <pdfs>     # IS 808 / IS 811 / IS 1161 -> structured/sections.csv
python scripts/build_is875_1_table1.py                      # after the served Table 1 is clean
python scripts/serve_figure_transcriptions.py               # every line OK
python scripts/build_index.py                               # update_docs + per-doc repair + unified build + manifest
python scripts/strip_watermark.py --check
python scripts/validate.py --corpus                         # prints CORPUS: PASS (n/n); writes indexes/validate_corpus.json
python -m pytest -q tests                                   # only if tests/ exists
```

### 5.3 PDF-less build

Use it for quick iterations on transcriptions, figure records, served text and metadata. Structured rows and manual headings must already be in the indexes.

```bash
python scripts/serve_figure_transcriptions.py
python scripts/build_index.py --no-repair
python scripts/validate.py --corpus
```

- `--no-repair` carries clause bodies sliced from the PDF layout over from the previous `search/spec_fts.sqlite`. Do not delete that file between builds.
- Compare `indexes/build_stats.json` before and after. If `section_body_source.prior_build` drops and `page` rises, the previous FTS file was lost: rerun the with-PDF build.

### 5.4 After a with-PDF build

Compare `indexes/build_stats.json` (`sections_spec`, `tables_spec_with_id`, `fts_rows`) with the first-pass values. If many clause records disappeared (the reference build lost about 190 when the PDFs were not found), `source_pdf` is wrong: fix it and rebuild.

The reference build, for scale: 17 stems, about 2 200 sections, about 2 000 table records (1 000+ of them structured rows) and 118 probes.

### 5.5 Querying (for checks)

```bash
python scripts/search.py exact_section 7.2.6 --doc IS_1893_Part_1_2016 --no-cache
python scripts/search.py exact_table "Table 9" --doc IS_1893_Part_1_2016 --no-cache
python scripts/search.py exact_table "Fig. 10" --doc IS_875_Part_3_2015 --no-cache
python scripts/search.py fts "basic wind speed Chennai" --no-cache
python scripts/serve_http.py --host 127.0.0.1 --port <free port>    # optional: POST /query, GET /healthz
```

Modes: `exact_section`, `exact_table`, `exact_equation`, `fts`, `keyword`, `auto`, `id`. `--doc` accepts a stem or a collection name.

---

## 6. Procedure

Do the steps in order. Keep a running log (`<scratch>/log.md`) of every change: stem, pdf page, what, why and how verified. FIX_REPORT.md is built from it.

### 6.1 Inventory

1. **Unzip and list.** List `documents/standards/*`. For each stem, record the PDF page count (`pdfinfo`), the number of page markers in `search.md` and of `pages_search` files (all three must agree), the `documents.json` edition, title and quality, and whether the per-doc `indexes/*.json` exist.
2. **Match PDFs to stems** by the title page: standard number, part, year, "(Nth Revision)", and the amendment sheets present. Copy each as `<pdfs>/<STEM>.pdf`.
   - Separate amendment PDFs: IS 1893 Amd 1/Amd 2 go with `IS_1893_Part_1_2016`; the IS 811 Amendment is `IS_811_1987_Amd1_2011`.
   - Report unmatched PDFs and stems without a PDF (section 2).
3. **Classify every page:** *born-digital* (real text layer, `pdffonts` lists fonts), *scanned with an OCR layer* (one invisible font, noisy text) or *image-only* (`pdftotext` gives fewer than about 100 characters). The reference copies: IS 801, IS 811, IS 816, IS 875-2 and IS 875-5 are scanned prints; IS 800's text layer is OCR; the rest are born-digital, with CID-encoded glyph runs on some IS 875-3 and IS 1893 pages.
4. **Baseline.** Run the build (5.2) and the validator on the untouched first-pass corpus and save the output. FIX_REPORT.md reports before and after.
5. **Offset map.** For each stem, find the ref-page items of sections 6.3 and 7 by caption and note the offset.

### 6.2 Page-level text QA: every page of every supplied stem

For each page, render `pdftoppm -r 300 -f P -l P -png <pdf> <scratch>/<stem>_p`. Compare three things: the rendered page, the PDF text layer (`pdftotext -layout -f P -l P`) and the served segment.

1. **Image-only or scanned page:** OCR it (`tesseract <png> - --psm 6`, and `--psm 4` for tables) and read the render yourself. The served text must hold every clause, heading, table caption, note and footnote on the page. Rebuild the page text from the OCR, corrected against the image.
2. **Coverage check** (every page): tokens of 4 or more letters in the text layer (or OCR) against tokens in the served text, after dropping page furniture. Coverage below about 90 %, or served text much shorter than the text layer, means lost text: repair it.
3. **Character-level defects** to look for (all seen in first passes):
   - OCR confusions I↔1↔l, O↔0, S↔5, B↔8, rn↔m, fl/fi ligature loss ("fllet"), "arc" for "are", "cumbinations";
   - glyph confusions in symbols: γ read as y, χ as x or ~, φ as ¢, √ lost, ≤ ≥ lost or swapped, ° lost, subscripts split ("k 2", "γ m0") or merged;
   - decimal points dropped or moved, thin spaces read as "0";
   - Docling math-italic Unicode (𝜀 𝑅 𝑦): normalise to plain letters;
   - LaTeX blocks with spaced digits (`1 5 ^ { \circ }`);
   - inequalities scrambled into word order ("5 15 3 m l m ≤ ≤");
   - words split by line-end hyphens;
   - two-column pages interleaved line by line (common in IS 1893 and IS 875-3). Linearise them.
4. **Correct each defect in both served files.** Correct only what the page image shows: every corrected character must be visible on the render. Where the print itself is wrong, keep it and tag `[sic]`.
5. **Page markers:** `printed_label` equals the printed folio. Fix covers that carry a year and pages whose label is shifted by one.
6. **Headings:** every clause and sub-clause id on the page is a heading line (4.1). After the rebuild, `exact_section <id>` must hit this page.

### 6.3 Tables: every numbered table the engines use

For each table below: find it on the page image; compare every cell of the served grid with the image; if any cell, header, note or row order is wrong, transcribe it (4.3); rebuild; then check `exact_table "<id>" --doc <STEM>` and one full-text query built from the caption words. The top hit must show the transcription, not the grid.

★ = the engines cite it heavily; T = transcribed in the reference build (the first pass will not have it, so do it again).

| stem | tables to check (ref page) |
|---|---|
| IS_800_2007 | ★2 (24, T) limiting width-to-thickness; 3 (26) max effective slenderness; ★4 (35, T) γf; ★5 (36) γm; ★6 (37, T) deflection limits; ★7 (41) imperfection factor; 8(a)–(d) (42–45) χ; ★9(a)–(d) (46–49) fcd (4–19 % of converted cells wrong: transcribe all four); ★10 (50, T) buckling class; ★11 (51) effective length; 12 (54); 13(a)(b) (61–62); 14 (63); 15, 16 (64, 67); 17 (77); ★18 (78) equivalent uniform moment factor; ★19–22 (79–84; the engines cite 20 and 22); ★23 (93) R, flagged against IS 1893 Table 9; 26(a)–(d) (99–104) fatigue details, **not transcribed yet**; 42 (135) c1, c2, c3 (used for Mcr) |
| IS_801_1975 | ★Table 2 (12, T) basic design stress; the 5.2.1.1 table (7, T); any other table on the hand-repaired pages 7–9, 12, 14–26, 31–33 |
| IS_808_2021 | Tables 1–16 (8–48): served by `sections.csv` rows (6.6). Grids are superseded; captions must still be detected on the first page of each table, not only "(Continued)/(Concluded)" |
| IS_811_1987 | Tables 1–10 (8–30): `sections.csv` rows; ★11 (31, T) 90° corner: three cells were unverified (7.3) |
| IS_1161_2014 | Table 1 (4): `sections.csv`; ★Table 2 (6) tensile properties; Tables 3, 4 |
| IS_2062_Part_1_2025 | Table 1 (5) chemical composition; ★Table 3 (9) mechanical properties by thickness band (engines take plate fy from it) |
| IS_4000_1992 | ★Table 2 (5) permissible forces; ★Table 3 (8) minimum bolt tension; Tables 1, 4 |
| IS_816_1969 | every table: in the reference build **no caption survived OCR**. Restore every caption, and transcribe the weld-size and throat tables |
| IS_9595_1996 | Tables 1–10 and 9A–9C (42–52): captions OCR-garbled ("Table 98" is 9B; 5 and 9 missing). Fix the captions; transcribe any table whose cells are wrong |
| IS_875_Part_1_2026 | ★Table 1 (4–28) unit weights (K04, 4.6); Table 2 (29) stored materials |
| IS_875_Part_2_1987 | ★Table 1 (9–13, T, one entry per page) occupancy floor loads; ★Table 2 (16, T) roofs, plus a canonical line for its sloping-roof rule; Table 3 (17, T) parapets; the tables in 3.1.2 and 3.2.1 (14, T) and 6.3 crane loads (17, T); check whether Amd 1 changes any row (4.4) |
| IS_875_Part_3_2015 | ★1 (9) k1; ★2 (10, T) k2; 3 (10); ★4 (12, T) Ka; ★5 (15, T) Cpe walls; ★6 (16, T) Cpe pitched roofs; ★7 (17, T) monoslope; 8, 9 (19, 20, T) free roofs; 10–17 (21–28; 11 T); 18 (29, T) curved; 19, 20 (30, 32); 21, 22 (33, 34, T); 23, 24; ★25 (38–40) Cf clad buildings, **not transcribed yet**; 26; 27–31 (42–44, T); 32–36 (45–50); the k4 table in 6.3.4 (11, T, id `6.3.4-k4`); ★Annex A (53, T) town wind speeds |
| IS_875_Part_4_1987 (2021) | the tables and coefficient lists in 5.2.1–5.2.6 and Annex A (A-2, A-3, A-5) |
| IS_875_Part_5_1987 | the 8.1 combinations list a)–n) with Notes (18–19); any table on the scanned pages |
| IS_1893_Part_1_2016 | 1, 2 (12); ★3 (12, T) Z; 4 (15) soil types; ★5 (16 + 18, T, **as amended**) plan irregularities; ★6 (18–19, T, as amended) vertical irregularities; ★7 (21, T) minimum lateral force (the exact hit must be p. 21, not the p. 22 mention); ★8 (21, T, as amended) importance factor; ★9 (22, T, as amended, Note 1 on OMRF/OBF in Zones III–V) R; ★10 (22, T) imposed-load percentage; the Sa/g spectrum rows of 6.4.2 (11, T, id `6.4.2-Sa/g`); ★Annex E town zone table |
| IS_18168_2023 | ★Table 1 (7) Ry, Ru; ★Table 2 (8, T) width-to-thickness limits: fraction forms, the Links / closed-box cell, the Ca / ε footnote |

**Continuation pages.** A table spanning pages needs a caption on its first page. Following pages carry "(Continued)" or inherit the id. Check that `exact_table` returns the caption page first.

### 6.4 Figures to transcribe

**Digitisation method.** Use it for every graph. Write your own tracer; the pixel coordinates of any earlier trace do not apply to your scan.

1. **Render and preprocess.** Render the page at 300 dpi (`pdftoppm -r 300 -f P -l P -png`), and at 600 dpi for fine detail; keep renders in `<scratch>` only. Load it greyscale and threshold to ink (about < 150 of 255). For colour maps, sample each legend swatch and assign each pixel to the nearest legend class.
2. **Correct the rotation.** Scans are typically rotated 0.5–1.5°; an uncorrected ~1° rotation biased earlier point readings by 5–9 %.
   - Fit `row = a + b·col` to the x-axis and `col = a' + b'·row` to the y-axis (or grid lines), from dark-run centres, rejecting outliers beyond 3 px.
   - Project each pixel onto the fitted axes before converting: `c' = c − b'·(r − (a + b·c))`, `r' = r − b·(c − (a' + b'·r))`.
3. **Calibrate from the tick pixels.** Detect the tick marks (or grid-line centres) on each axis and pair them with the printed tick labels. Convert by piecewise-linear interpolation between neighbouring ticks, not one global scale; this absorbs paper stretch.
   - **Log axes:** interpolate `log10(value)` between labelled ticks and exponentiate. Check that the minor ticks (2 … 9 × decade) fall where `log10` predicts, within 2 px.
4. **Trace the curves.** Follow each curve column by column from a seed, predicting the next row from the local slope and accepting the nearest dark run within a window. Tell solid from dashed by run pattern. Through crossings and labels, use a guided trace: place waypoints by eye, collect runs within ±tol, re-fit a local quadratic. Overlay every trace on the render and look at the overlay before accepting it.
5. **Read the values.** Read at the abscissae the figure's use needs and at every printed grid value, fitting a local line (in log space for log axes) through the traced points within ±0.1 of the target. Report 2 significant figures, plus peaks (value and position).
   - Validate every figure: pick 5 or more check points per curve, read them by eye on a zoomed crop, and compare. The difference must be inside your stated uncertainty.
6. **Maps.**
   - **Georeference** with 6 or more control points (graticule intersections, or printed town dots and state trijunctions with known coordinates). Fit an affine pixel↔(lon, lat) transform, report the RMS residual in km, and check it on 3 extra places.
   - Read the zone or band at each town's coordinates by majority class in a window about 1–2 km across.
   - **Flag a boundary town** if another class occurs within ~10 km (sample rings at 2.5, 5, 7.5 and 10 km). Write "boundary: EOR confirm" and name the other zone.
   - Town coordinates and altitudes come from general reference, not from the standard: label them so.
7. **Provenance statement** (rule 8.3) with the uncertainty. Typical: ±10 % for curve readings (±20 % on steep branches); ±0.03 for coefficient charts; ±1 zone or band within ~10 km of a boundary; "printed values (exact)" when the figure prints its numbers.
8. **Errata and amendments.** Apply any amendment or erratum that corrects the figure (a caption swap, relabelled axis ticks), and say so in the reading notes.

**Figures to do.** Ids are exact `table_id`s.

| stem | id (ref page) | what the record must hold | uncertainty |
|---|---|---|---|
| IS_875_Part_3_2015 | `Fig. 1` (8) wind map | a georeferenced town table of Vb for every district HQ and every town the user names that is absent from Annex A (at least Kochi, Noida, Gurugram, Indore). Row format per 4.7 | ±1 band at an edge |
| IS_875_Part_3_2015 | `Fig. 2` (14 + amendment sheet) Cpi, one open side | the printed Cpi values per case (B/L cases), as amended | printed |
| IS_875_Part_3_2015 | `Fig. 3` (≈31) Cpe upper roof, cylindrical structures | digitised curves | ±0.03 |
| IS_875_Part_3_2015 | `Fig. 4` (37) Cf, rectangular clad buildings | Cf vs a/b for every printed h/b curve, both panels (a)(b), at the a/b grid 0 … 3 | ±0.03 |
| IS_875_Part_3_2015 | `Fig. 5` (≈41), `Fig. 6` (≈45), `Fig. 8` (≈47) | Fig. 5 Cf vs Re; Fig. 6 effective solidity ratio; Fig. 8 zone description plus factors | as read |
| IS_875_Part_3_2015 | `Fig. 10` (51), `Fig. 11` (52) across-wind Cfs | Cfs at x = V̄h,d/(fc·b) = 2, 3 … 16, plus the peak value and position, for every curve (h:b:d ratios; solid and dashed turbulence-intensity sets). Apply the amendment or erratum that corrects the Fig. 10 x-axis tick labels. Log y axis | ±10 % (±20 % steep branches) |
| IS_875_Part_3_2015 | `Fig. 14`, `Fig. 15` (57) topography s0 (Annex C), captions **swapped by Amendment 1** | contour intercepts on the crest and ground lines, and s0 on the grid x/Le = −1.5 … 2.5 (step 0.25) × H/Le = 0 … 2.0 (step 0.25) by contour interpolation | ±0.03 |
| IS_875_Part_4_1987 | `Fig. 1` (12) snow zone map (J & K, Ladakh, HP, UK) | the georeferencing (control points, residual); zone Z at every district HQ and hill town of the four regions (the reference read 73) with type, state, lat, lon, boundary flag, other zones within ~10 km, and indicative altitude; the A-3 s0 table by zone × altitude, labelled "computed from the printed A-3 rule"; the `outside the mapped area` line (4.7) | ±1 zone near boundaries |
| IS_875_Part_4_1987 | `Fig. 2` (13) Sikkim s0 map | s0 at Gangtok, Namchi, Gyalshing, Mangan, Lachung, Lachen, Nathula and other district HQs, with boundary flags | as read |
| IS_875_Part_4_1987 | `5.2.1-shape`, `5.2.2-shape`, `5.2.3-shape` (4–6) | the μ1 / μ2 values and expressions printed in the sketches, per roof case; flag any printed constant that contradicts the text [sic?] after checking the image | printed |
| IS_875_Part_4_1987 | Fig. 3 (14) | none needed: it plots the A-5 equation, which is in the text. Add a one-line note record or leave it | — |
| IS_1893_Part_1_2016 | `Fig. 1` seismic zone map | zone descriptions; georeferencing (fit the graticule); a town table for the towns absent from Annex E that the engines hit (at least Noida, Ghaziabad, Gurugram, Indore) plus district HQs of the states the user names; boundary flags within 10 km; `section_id` 6.4.2 (Z from Table 3) | ±1 zone near boundaries |
| IS_1893_Part_1_2016 | `Fig. 6` (image near 7.6.4) diaphragm flexibility sketch | its caption is lost in the first pass. Restore the caption verbatim, and add a record describing the printed geometry: the deformed-diaphragm chord, the maximum displacement from the chord and the average displacement. No numbers beyond what is printed. The engines apply 7.6.4 from it | printed |
| IS_1893_Part_1_2016 | Figs 2–5, 7–10 | Fig. 2 is covered by the 6.4.2 spectrum rows and canonical lines. Figs 3–4 are irregularity sketches (Amd 2 deletes parts of Fig. 4). Figs 8–10 have captions substituted by amendment. Restore the captions only | — |
| IS_18168_2023, IS 1893 Annexes A–C | drawings and informative maps | no values; captions present | — |

**Seismic zone reading.** The retrieval code quotes a map reading in the `not_tabulated` note only for wind. The seismic record is reachable by `exact_table "Fig. 1" --doc IS_1893_Part_1_2016`; propose the seismic note branch as a code change. `fts "Noida zone"` must still answer `not_tabulated`.

### 6.5 Equations with broken OCR

For every clause below, compare the served formula with the page image. If any symbol, operator, exponent or coefficient is wrong or missing, add a canonical line (4.2) after it. Probe with `exact_section <clause>`: the text must contain a key token of the canonical line.

| stem | clauses |
|---|---|
| IS_800_2007 | 6.4.1 (block shear), 7.1.2.1 (fcd), 7.4.3.1 (slab base), 8.2.2 (Md), 9.3.2.2 (interaction), 10.3.3, 10.3.5, 10.5.7.1.1, 12.11.3.2; also 3.8 / Table 3, 5.6.1, 8.2.1.2, 8.2.2.1 (Mcr, uses Table 42), 9.3.1.2, 10.4.3, 12.2.3 |
| IS_801_1975 | 5.2.1.1 (effective width), 6.1 / 6.1.2 (basic stress and its wind/earthquake increase), 6.6.1.1–6.6.1.2, 6.7, 7.3–7.5, 8.1 including 8.1(d) P_min (see 7.2); the combined-stress interaction (the second bending term's subscript is misprinted: [sic]) |
| IS_875_Part_3_2015 | 6.3 (Vz), 6.3.2.2, 6.3.3, 6.3.4, 7.2 (pz, pd, Kd, Ka, Kc), 7.3.1–7.3.2.2; **10.2 gust factor**: the print writes a symbol that is not the one defined in the "where" list inside the squared term. Keep it with [sic] and add a canonical line with the defined symbol, as the page's own definitions require. **10.3 across-wind**: the peak factor g_h and the moment M_c expressions are OCR-broken; add canonical lines for both from the page image. Check the erratum pages of the licensed copy for corrections to 10.2 and 10.3 |
| IS_875_Part_4_1987 | 4.3, 4.4, 5.2.4 (the angle condition prints ">" where the rule that follows requires the complementary condition: keep it, [sic], canonical line), 5.2.5 and 5.2.6 (μ2 bounds and drift-length bounds: canonical lines), Annex A-2, A-3 (s0 expression), A-5 |
| IS_875_Part_5_1987 | 8.1: the full combinations list a)–n) and Notes as canonical lines; item h) was garbled beyond recognition (7.2) |
| IS_875_Part_2_1987 | 3.1.2, 3.2.1, 4.x, 6.3; the Table 2 sloping-roof rule |
| IS_1893_Part_1_2016 | 6.3 combinations (6.3.2.2, 6.3.3.1, 6.3.4 as amended), 6.4.2 (Ah; Sa/g for both methods and all soil types), 7.2.1, 7.2.2 (ρ, Table 7), 7.3.6, 7.6.2 (Ta, all systems), 7.7.3 (scaling to V̄B), 7.7.5, 7.8.2 (design eccentricity), 7.11.1.1 (drift), 7.11.2, 7.11.3 |
| IS_18168_2023 | 5.2, 5.3, 5.5 (overstrength combinations and Ω), 7.5, 8.2 (SCWB), 9.3, 10.4.1, 11.1(c), 11.2–11.4 (link strengths and welds), 12.3.2.2, 12.3.3.1, 12.3.4.4. Docling's formula model output: verify every numeric coefficient |

### 6.6 Section-property tables (IS 808, IS 811, IS 1161)

1. Run `build_section_tables.py --pdf-dir <pdfs>`. Read `sections_check.json`: every row in `unresolved` must be settled by you.
2. **Cross-check every row** by computing it from its own dimensions. Tolerances are ±1 % unless stated.
   - Mass = 0.785 × A (kg/m with A in cm²).
   - r = √(I/A).
   - Z = I/c. For an I section c = D/2; for the minor axis c = B/2 (I) or B − Cy (channel); angles use their printed centroid distances.
   - The designation's dimensions equal the dimension columns.
   - **IS 808 plate-area check (±5 %):** A ≈ 2·B·tf + (D − 2tf)·tw + k·(1 − π/4)·R1², with k = 4 for I sections and 2 for channels. Use the mean tf for sloping flanges. Angles are not checked.
   - **IS 808 inertia sanity (±8 %):** Ixx ≈ [B·D³ − (B − tw)(D − 2tf)³]/12 for I sections. Use it to catch digit errors, not to correct.
   - **IS 1161 CHS:** A = π·t·(D − t); I = π·[D⁴ − (D − 2t)⁴]/64; Z = 2I/D; r = √(I/A).
   - **IS 811 thin-walled model:** centre-line geometry with the inside corner radius relation printed in the standard. Compute A, I, the centroid, J, x0 and Cw. Table 11 (90° corner) uses the thin-wall arc: A, I and the centroid of a quarter annulus.
3. For each failing or unresolved row, read the row on the 300–600 dpi page image.
   - **If the first pass misread it:** correct the cells, set `check` to `PASS (corrected from PDF p.P, <date>)`, remove the row from `unresolved`, and (IS 811) record the reads in `is811_manual.json`.
   - **If the print itself is inconsistent:** keep the printed values, set `check` to `FLAG: misprint in the standard — <which relation fails>`, and list the row in `unresolved` with the reason.
4. **Quarantine rule.**
   - A row that fails the plate-area check is `QUARANTINED` automatically by `apply_section_checks`. Its values stay as printed, and its record title says "do not use".
   - **Never adjust a value so that a check passes.** Clear a quarantine only by reading the PDF.
   - To re-run the checks alone: `python -c "import sys; sys.path.insert(0,'scripts'); import corpus_fixes as c; from pathlib import Path; c.apply_section_checks(Path('.'))"`.
5. With-PDF rebuild. Then check `exact_table "HB 300" --doc IS_808_2021`, `exact_table "168.3x6.3" --doc IS_1161_2014` and `exact_table "CLR100X50X15X2" --doc IS_811_1987`: each returns one row record with the printed values.

### 6.7 Watermark stripping

Run `strip_watermark.py --apply` over `documents` and `indexes`, then `--check`. Grep the whole tree, including file names and CSV cells, for the licensee's name, user id, IP and any `@`. Rebuild, so the FTS index is regenerated from clean text, and confirm the validate watermark probe passes. Do it again after every step that pastes text from the PDF.

### 6.8 Metadata and edition labels

For every stem, check `documents.json` against the title page (4.10) and fix: the edition, `title` (the full printed title), `standard` (for example `IS 875 (Part 4):2021`), `amendments`, `amendment_pages`, `reaffirmed`, `collection_name`, `family`, `image_only` (the figures that remain images), and `quality` / `known_defects` (also in `scripts/quality.json`) to match what you fixed and what remains. First-pass metadata is often wrong: a year from a foreword, the stem's year, a title of "IS 875 Part 4 1987".

### 6.9 Aliases

After the build, run the checks of 4.8 and these queries: `fts "Bengaluru"` (top two hits IS 875-3 Annex A and IS 1893 Annex E); `fts "Vizag"` and `fts "Cochin"` (resolve); `auto "Ω0"` (`found:false` with the IS equivalent); `fts "response reduction factor"` (IS 1893 first).

### 6.10 Rebuild

Run the full with-PDF build (5.2) and check `build_stats.json` against the baseline. Then remove the `source_pdf` paths (4.10) and rebuild with `--no-repair`, so the indexes carry no local paths.

### 6.11 Validate

Run `python scripts/validate.py --corpus`. It must end `CORPUS: PASS (n/n probes)`.

- For each probe that fails, fix the corpus, not the probe.
- There are four legitimate exceptions. List each in FIX_REPORT.md under "Probe exceptions", with its evidence:
  - the document was not supplied;
  - the user's edition differs;
  - pagination differs (a page-number probe that fails by exactly the offset you recorded);
  - a figure value probe whose expected string differs from your careful reading within the stated uncertainty.
- **Never write text that is not true in order to pass a probe.** For example, do not write "Public.Resource.Org" into a provenance line if you did not use that copy.

**The full probe list** (validate.py `--corpus`, reference build: 118 probes). Use it to verify by hand if validate.py is missing.

- "Key" means that text must be in the hit.
- `<…>` means: read the value from your PDF and check that it is present.
- Collections: prefix `engineering_standards_` to the short name.

| # | probe (type, query / id, doc) | collection | expected key |
|---|---|---|---|
| 1–10 | `exact_section` 6.4.2, 7.2.1, 7.2.6, 7.3.6, 7.6.2, 7.6.2.1, 7.7.1, 7.7.3, 7.8.2, 7.11.1.1 — IS_1893_Part_1_2016 | IS1893 | found; hit section_id equals the id; 7.2.6 contains "Table 9"; 7.3.6 contains `<the minimum partition load value>` |
| 11–21 | `exact_section` 5.3.3, 7.1.2.1, 8.2.2, 12.2.3, 12.7.2.1, 12.8.3.1, 12.11.3.2, D-1, D-2, Annex D, E-1.1 — IS_800_2007 | IS800 | found; D-1 contains "effective length"; Annex D contains "EFFECTIVE LENGTH" |
| 22 | `exact_section` 5.2.4 — IS_875_Part_4_1987 | IS875_P4 | the canonical angle condition, the μw bounds and the l3 bounds, in the canonical-line notation |
| 23 | `exact_section` 8.1 — IS_875_Part_5_1987 | IS875_P5 | "h) DL+IL+TL", "j) DL+WL+TL", and the Notes' dead-load factor phrase |
| 24 | `exact_section` 8.5 — IS_811_1987_Amd1_2011 | IS811_Amd1 | "IS 1852" |
| 25–29 | `exact_section` 6.3.1, 6.3.2, 6.3.3, 6.3.4, 7.2 — IS_875_Part_3_2015 | IS875_P3 | found; 6.3.4 contains `<the two k4 values>` |
| 30 | `exact_section` 3.1.2 — IS_875_Part_2_1987 | IS875_P2 | found |
| 31–33 | `exact_section` 5.2.1.1, 6.1, 6.6.1.1 — IS_801_1975 | IS801 | found |
| 34–37 | `exact_section` 1, 5.5, 11.3, 12.3.3.1 — IS_18168_2023 | IS18168 | 1 contains "SCOPE"; 5.5 contains "Overstrength" and `<both Ω values>`; 11.3 and 12.3.3.1 each contain `<the value printed in the clause>` |
| 38–42 | `exact_table` 3, 7, 8, 9, 10 — IS_1893_Part_1_2016 | IS1893 | hit table_id equals the id and its text contains "Table N" |
| 43–46 | `exact_table` 4, 5, 6, 10 — IS_800_2007 | IS800 | same |
| 47–51 | `exact_table` 1, 2, 4, 5, 6 — IS_875_Part_3_2015 | IS875_P3 | same |
| 52–53 | `exact_table` 1, 2 — IS_875_Part_2_1987 | IS875_P2 | same |
| 54 | `exact_table` 7 — IS 1893 | IS1893 | first hit is the caption page (ref p. 21), not the p. 22 mention |
| 55 | `fts` k4 (no doc) | — | top hit IS_875_Part_3_2015, the 6.3.4 page (ref p. 10–11) |
| 56 | `exact_table` 2 — IS_801_1975 | IS801 | `<two basic design stress values>` served; OCR garbage "M1NoIuu" / "YIBLD" absent from the hit and the title |
| 57 | `exact_table` 4 — IS_800_2007 | IS800 | "γf" + `<one load factor>`; "y~," absent |
| 58 | `exact_table` 10 — IS_800_2007 | IS800 | "Buckling Class"; "(3am" absent |
| 59 | `exact_table` 2 — IS_875_Part_3_2015 | IS875_P3 | column header "Terrain Category 3, k2 (5)" + `<two k2 values>`; the converted title "Terrain and Height Multiplier ( k 2 )" absent |
| 60 | `exact_table` 2 — IS_18168_2023 | IS18168 | fraction forms "…ε/√Ry" restored `<with printed coefficients>`; the split math-italic form ("𝜀 √𝑅 y") absent |
| 61 | `exact_table` 11 — IS_811_1987 | IS811 | `<a Ri value>`; "UNVERIFIED" gone once you fill the three cells (the reference probe still expects it: note the change); "I.87" OCR form absent |
| 62 | `fts` "Table 2 basic design stress yield" — IS_801_1975 | IS801 | top hit has the transcription; not "M1NoIuu" |
| 63 | `fts` "Table 4 partial safety factors for loads" — IS_800_2007 | IS800 | top hit has "γf"; not "y~," |
| 64 | `fts` "plain cement concrete sand and gravel" — IS_875_Part_1_2026 | IS875_P1 | top hit has `<the printed unit-weight range>` |
| 65 | `fts` "steel sections density" — IS_875_Part_1_2026 | IS875_P1 | top hit has the steel density with the [sic] unit note |
| 66 | `fts` "reinforced cement concrete 2 percent steel" — IS_875_Part_1_2026 | IS875_P1 | top hit has `<the printed range>` |
| 67 | `exact_table` "Fig. 10" — IS 875-3 | IS875_P3 | peak line "`<value>` at x ≈ `<x>`" per curve; the corrected x-tick sequence; provenance with "confirm against the licensed copy" |
| 68 | `exact_table` "Fig. 11" — IS 875-3 | IS875_P3 | curve label "6:1:2"; peak lines; provenance |
| 69 | `exact_table` "Fig. 4" — IS 875-3 | IS875_P3 | curve labels "h/b = ∞" and "h/b = 1/4"; a table row "`| a/b | … |`"; provenance |
| 70 | `exact_table` "Fig. 2" — IS 875-3 | IS875_P3 | the printed Cpi values with sign (Unicode minus "−"); provenance |
| 71 | `exact_table` "Fig. 1" — IS 875-3 | IS875_P3 | "Kochi (Cochin)", "Noida", a Vb cell `| <value> |`; provenance |
| 72 | `exact_table` "Fig. 14" — IS 875-3 | IS875_P3 | "Cliff and Escarpment" + intercept rows; provenance |
| 73 | `exact_table` "Fig. 15" — IS 875-3 | IS875_P3 | "Ridge and Hill" + intercept rows; provenance |
| 74 | `exact_table` "Fig. 1" — IS_875_Part_4_1987 | IS875_P4 | "`| Srinagar |`", "boundary: EOR confirm", the A-3 s0 expression, the georeferencing equations; provenance |
| 75–77 | `exact_table` "5.2.1-shape", "5.2.2-shape", "5.2.3-shape" — IS 875-4 | IS875_P4 | the μ expressions of each case; provenance |
| 78–89 | `auto` queries → figure record in the top k: "across wind force spectrum coefficient" → Fig. 10 (k 2); "across wind force spectrum coefficient Cfs values (Fig. 10 / Fig. 11)" → Fig. 11 (k 2); "Fig. 2 large openings in buildings values of internal pressure coefficients" → Fig. 2 (k 2); "force coefficients for clad buildings of uniform section Figure 4", "7.4.2.1 force coefficients rectangular clad buildings a/b h/b Fig. 4", "Fig. 4 force coefficient rectangular clad building (figure values)" → Fig. 4 (k 1); "Himachal Pradesh zone map snow" → IS 875-4 Fig. 1 (k 2); "Fig. 1 snow zone map Srinagar zone number", "snow load Chandigarh" → IS 875-4 Fig. 1 (k 1); "5.2.1 pitched roof shape coefficient", "Monopitched and Simple Pitched Roofs" → 5.2.1-shape (k 1); "Annex C topography factor s ridge hill figure" → IS 875-3 Fig. 15 (k 1) | IS875_P3 / P4 | found, and the id is in the top k |
| 90–92 | `exact_table` "Figure 10", "FIG. 11", "fig 4" — IS 875-3 | IS875_P3 | ids returned are exactly ["Fig. 10"], ["Fig. 11"], ["Fig. 4"] |
| 93 | `exact_section` "Figure 10" — IS 875-3 | IS875_P3 | returns only the Fig. 10 record |
| 94 | `exact_table` "Fig. 1" — IS 875-3 | IS875_P3 | returns only "Fig. 1" (not Fig. 10 or 11) |
| 95 | `exact_section` 5.2.1 — IS 875-4 | IS875_P4 | serves the 5.2.1 shape-coefficient expression |
| 96 | `fts` "snow load Srinagar" | — | top hit table_id "Fig. 1", snippet has "`| Srinagar |`" and its zone cell |
| 97 | `fts` "Kochi basic wind speed Annex A" — IS 875-3 | IS875_P3 | found false, not_tabulated true, note contains "Vb = `<reading>` m/s" |
| 98 | documents.json of IS_875_Part_4_1987 | — | title has 2021 and not 1987; standard = "IS 875 (Part 4):2021" |
| 99 | `exact_table` "CLR100X50X15X2" — IS_811_1987 | IS811 | exactly one hit; title has "Table 6" and "100 x 50 x 15 x 2.00" |
| 100 | IS 808 sections.csv | — | every I/channel row within ±5 % plate area or QUARANTINED; WPB 280 X 280 X 284.13 still QUARANTINED, or, if you corrected it from the PDF, PASS (note the probe change) |
| 101–102 | "Annex D" (auto) and `fts` "effective length Annex D" — IS_800_2007 | IS800 | top hit is the annex text (ref p. 128–129), never a contents page |
| 103 | `fts` "development length" — doc IS_456_2000 | — | found false, note exactly "IS_456_2000 is not in the corpus" |
| 104 | `exact_table` "HB 300" — IS_808_2021 | IS808 | table_id "HB 300", `<its printed mass>` |
| 105 | `exact_table` "168.3x6.3" — IS_1161_2014 | IS1161 | `<its I in mm⁴>` |
| 106 | `fts` "Bengaluru" | — | top two docs = IS 875-3 (Annex A) and IS 1893 (Annex E) |
| 107 | `fts` "Noida zone" | — | found false, not_tabulated true |
| 108 | `auto` "Ω0" | — | found false, us_term set |
| 109 | `fts` "response reduction factor" | — | top hit IS_1893_Part_1_2016 |
| 110 | `fts` "characteristic ground snow load" — doc IS_875_Part_4_2021 | IS875_P4 | resolves; hit edition "2021" |
| 111–116 | editions | — | IS_800_2007 "2007", IS_2062_Part_1_2025 "2025", IS_811_1987_Amd1_2011 "2011", IS_1893_Part_1_2016 "2016+A1+A2", IS_875_Part_4_1987 "2021", IS_18168_2023 "2023" |
| 117 | indexes/aliases.json | — | no "SDS", "S_DS", "Cd", "Steel02", "forceBeamColumn" groups |
| 118 | every .md/.json/.jsonl/.txt/.csv under documents/ and indexes/*.json | — | no watermark, no non-BIS e-mail |

**Add a probe for every new item** in FIX_REPORT.md (a query and a short key), and for every figure and table you transcribe, so the user can extend validate.py.

### 6.12 Package

1. Delete `cache/`, `queue/`, `__pycache__/`, `*.bak*` and every page image or PDF under `<corpus>`.
2. Set `source_pdf` to `null`.
3. Run `strip_watermark.py --check` a final time, and the validator a final time.
4. Zip the layout of 1.2: `cd <corpus> && zip -r ../corpus_fixed.zip documents indexes search INDIA_MANIFEST.json FIX_REPORT.md [scripts/<changed data files>]`.
5. List the zip contents, and check that it holds no `.pdf`, `.png` or `.jpg`, and no `.py`.
6. Give the user the zip and FIX_REPORT.md.

---

## 7. Known defects checklist

These were found in first-pass conversions of the same documents. Expect each one in your first pass. Check it, fix it as described, and report it.

### 7.1 Corpus-wide

- **Licence watermark** on every page and in JSON, CSV and FTS. See 4.11 and 6.7.
- **CID glyph-code mojibake** (`G6B G6F G3A …`) from Docling on born-digital IS 875-3 and IS 1893 pages, including figure labels and captions.
  - Move it into a comment.
  - For IS 1893 the searchable body had to be rebuilt from the `pdftotext` text layer (kept in `markdown/pages_recovered/`).
  - Restore any caption that was lost with it.
- **Two-column interleaving** in the `pdftotext -layout` text. A left-column clause and a right-column formula share a line. Linearise it.
- **Converted grids served on search paths** after a transcription existed. Hence the K02 pattern: the transcription must replace the grid everywhere, and probes check that garbled strings are absent.
- **Tables not recognised**: the caption was garbled, or it was a text mention only. See the caption rule in 4.1. Text mentions must not become table records.
- **Clause ids missing**: headings garbled, annex ids not indexed ("Annex D" answered by the contents page). Annex ids `D-1`, `E-1.1` and `Annex D` must be exact sections. Contents pages are flagged and demoted.
- **Page labels**: covers labelled with a year; shifted folios.
- **Docling formula output**: math-italic Unicode, LaTeX with spaced digits, lost fractions and radicals. Canonical lines.
- **Metadata**: editions and titles from the wrong line.

### 7.2 Per standard

| stem | defect (reference build) | fix |
|---|---|---|
| IS_800_2007 | The text layer is OCR. Stray character errors are in prose everywhere | Page QA (6.2) on every page the engines cite (clauses in 6.5) |
| IS_800_2007 | Tables 2, 4, 6 and 10 grids garbled ("y~,", "(3am") | Transcribe (K02) |
| IS_800_2007 | Table 9(a)–(d) fcd: 4–19 % of the converted cells wrong | Transcribe all four, and cross-check each cell with 7.1.2.1 computed fcd (differences only from rounding) |
| IS_800_2007 | Captions garbled: Tables 7, 12, 14, 17, 18, 42 ("et", "?/s m a", "cl, Czand c~") | Correct the caption lines; check the grids |
| IS_800_2007 | Table 26(a)–(d) fatigue details (ref pp. 99–104): the pictograms are mixed into the cells | Transcribe every row: detail number, constructional detail described in words, detail category, requirements. One file per sub-table, one index entry per page (26(b) has three pages) |
| IS_800_2007 | 12.8.2.2 is served ending "(only hangers)". Unknown whether printed or column bleed (ref p. 95) | Read the page. If printed, keep it and tag it; if bleed, remove it from both files and add a canonical line |
| IS_800_2007 | Formulas in 6.4.1, 7.1.2.1, 7.4.3.1, 8.2.2, 9.3.2.2, 10.3.3, 10.3.5, 10.5.7.1.1, 12.11.3.2 broken | Canonical lines (reference: "restated from the page image") |
| IS_800_2007 | Table 23 R values conflict with IS 1893 Table 9 | Keep as printed. The alias conflict rule flags it (no corpus edit) |
| IS_801_1975 | Scanned 1975 print; OCR everywhere; pp. 7–9, 12, 14–26 and 31–33 needed hand repair | OCR plus image read of every page; Table 2 and 5.2.1.1 transcriptions |
| IS_801_1975 | Headings 6.1 (text layer "~.l Baaic Des. Stre••") and 7.5.4 garbled | `bis_manual_sections.json` + served heading lines |
| IS_801_1975 | p. 32, 8.1(d) P_min: a small glyph before the radical in the denominator was illegible even at 600 dpi in the reference copy | Read it at 600 dpi on your copy. If legible, add a canonical line naming the page. If not, keep `TODO(verify, pdf p. 32)`. Never infer it |
| IS_801_1975 | The interaction formula prints a wrong subscript on the second bending term | Keep it, `[sic]` with the evident reading |
| IS_811_1987 | Scanned; property grids with digit/letter confusions, dropped decimals, merged rows; designations with a dropped leading digit | `build_section_tables.py` (text layer + tesseract, checked by geometry); settle every unresolved row from the image; `is811_manual.json` |
| IS_811_1987 | Captions of Tables 7 and 9 not detected; Table 1 caption truncated | Restore the caption lines |
| IS_811_1987 | Table 11 (90° corner) not in `sections.csv`. Three cells unreadable in OCR: Ri at t = 3.15, I at t = 5.00, cx at t = 6.00 | Transcribe (K02); read the three cells from the image and check them with the thin-wall arc geometry; remove "UNVERIFIED" |
| IS_811_1987 | No engine labels | `apply_section_checks` writes `label` |
| IS_811_1987_Amd1_2011 | One-line sheet indexed as 0 sections | It substitutes an IS reference in clause 8.5. The build indexes it as section 8.5 from the "(Page N, clause 8.5) — Substitute …" line: keep that line intact |
| IS_808_2021 | Docling grids misalign designations | Superseded by `sections.csv` |
| IS_808_2021 | WPB 280 X 280 X 284.13: printed A and mass do not belong to its D, B, tw and tf (plate area about a third of the printed A) | QUARANTINED. Read the PDF row (ref p. 17). Correct it only if the first pass misread; else keep it quarantined with "misprint in the standard" |
| IS_808_2021 | Rows that carry misprints in the standard itself: WPB 340x300x290.64; three WPB 360x300 masses; MC 75 rz; MC 175* mass | Keep as printed, flagged in `sections_check.json` |
| IS_808_2021 | WB rows of Table 1 print a radius in cm | Documented repair in `repairs` |
| IS_1161_2014 | Thin spaces in numbers read as "0" | Documented repair |
| IS_1161_2014 | CHS 165.1x5.9: printed I inconsistent with its Z and r | Flag, do not correct |
| IS_1161_2014 | RHS/SHS are not in IS 1161 | They belong to IS 4923, not supplied: never add them |
| IS_816_1969 | Scanned 1969 print; OCR errors in the weld clauses ("fllet", "arc" for "are"); no table caption survived | Full OCR + image QA; restore every caption; transcribe the tables and the fillet weld throat and effective-length clauses |
| IS_875_Part_1_2026 | Table 1 converted cells duplicated across columns; indentation lost, so the sub-heading context is wrong | Clean the served grid, then `build_is875_1_table1.py` (K04) |
| IS_875_Part_1_2026 | The steel density is printed with a wrong unit | Keep it, `[sic — …]` with the evident unit |
| IS_875_Part_2_1987 | Scanned; Tables 1–3 and clauses 3.1.2, 3.2.1, 4.x, 6.3 were illegible in OCR | Transcribe; canonical line for the Table 2 sloping-roof rule |
| IS_875_Part_3_2015 | Tables 2, 4–9, 11, 18, 21, 22, 27–31, the 6.3.4 k4 table and Annex A garbled or scrambled | Transcribe (the reference build transcribed all of them) |
| IS_875_Part_3_2015 | Table 25 (Cf, clad buildings; ref pp. 38–40): plan-shape pictograms scrambled; cells "07", "8>" / "58"; a non-monotonic cell | Transcribe: plan shapes described in words with their printed ratios, the V̄d·b ranges and the Cf values. One index entry per page, id "25" |
| IS_875_Part_3_2015 | 10.2 gust factor prints an undefined symbol in the squared term | `[sic]` + canonical line (6.5) |
| IS_875_Part_3_2015 | 10.3 g_h and M_c formulas OCR-broken | Canonical lines from the page image |
| IS_875_Part_3_2015 | Figs 1, 2, 4, 10, 11, 14, 15 image-only; Fig. 10 x-axis tick labels misprinted, corrected by an erratum; Figs 14/15 captions swapped by Amendment 1 | Figure records (6.4) with the erratum and amendment applied |
| IS_875_Part_3_2015 | Towns absent from Annex A (Kochi, Noida, Gurugram, Indore) return not_tabulated | Correct behaviour. The Fig. 1 record adds a reading to the note; keep not_tabulated |
| IS_875_Part_4_1987 | Metadata title and standard read "IS 875 Part 4 1987" for a 2021 document | Edition 2021, full 2021 title, standard "IS 875 (Part 4):2021", `stem_alias` ["IS_875_Part_4_2021"], `supersedes` "IS 875 (Part 4):1987", `stem_note` |
| IS_875_Part_4_1987 | 5.2.1–5.2.3: the sketches hold the coefficients; the served text has only `<!-- image -->` | Shape records (6.4); `exact_section 5.2.1` must serve them |
| IS_875_Part_4_1987 | 5.2.2: one printed μ1 constant looks inconsistent with the text | Check the image. `[sic]` if printed; else correct |
| IS_875_Part_4_1987 | 5.2.4: the angle condition prints ">" where the following rule requires the complement (verified against an official BIS text); LaTeX with spaced digits; a scrambled bound inequality | Keep the print with `[sic]`; canonical lines for the condition and both bounds |
| IS_875_Part_4_1987 | 5.2.5, 5.2.6 bounds only in sketches or broken text | Canonical lines |
| IS_875_Part_4_1987 | Figs 1, 2 image-only (Fig. 3 plots A-5) | Figure records |
| IS_875_Part_5_1987 | Scanned; OCR noise in headings and notes ("Norx I", "cumbinations", "I'L = wind load") | Page QA |
| IS_875_Part_5_1987 | 8.1 item h) garbled beyond recognition ("71+71+TA (4"); the reference build restored it as DL+IL+TL from the list pattern **without a page image** | Read the item on the page (ref pp. 18–19); K02 block for item h); canonical 8.1 a)–n) + Notes; mark it "verified against the licensed PDF" |
| IS_1893_Part_1_2016 | Amendments 1 and 2 not consolidated | CORPUS-A blocks on every amended clause and table: at least 4.26 (new definition), 6.3.2.2, 6.3.3.1, 6.3.4 (title), Tables 5, 6, 8, 9 (incl. Note 1), 7.x clauses named on the sheets; figure deletions and caption substitutions noted. `amendment_pages` = the sheets |
| IS_1893_Part_1_2016 | Tables 3, 5–10 and the 6.4.2 spectrum grids garbled | Transcribe (as amended) |
| IS_1893_Part_1_2016 | Table 7 caption page vs a mention on the next page | The exact hit must be the caption page |
| IS_1893_Part_1_2016 | Annex E town table: two-column layout, spelling variants, the table continues onto the next page without a title | Keep the printed title line on the first page (it flags the page for town lookups); ensure every town row is one line "Town Zone Z-value" in reading order; the next page is read automatically |
| IS_1893_Part_1_2016 | Fig. 1 zone map image-only (Noida, Ghaziabad, Gurugram and Indore are not in Annex E) | Figure record (6.4); not_tabulated stays |
| IS_1893_Part_1_2016 | Fig. 6 (diaphragm flexibility, 7.6.4) is an image with its caption lost | Restore the caption; description record |
| IS_1893_Part_1_2016 | Annex A–C maps image-only | No values needed; captions only |
| IS_2062_Part_1_2025 | (reference: PASS) | Verify Table 3 cell by cell anyway: engines take fy by thickness band from it |
| IS_4000_1992, IS_9595_1996 | UNREVIEWED in the reference build; IS 9595 captions OCR-garbled ("Table 98" = 9B) | Full page QA; captions; transcribe the tables the engines use (IS 4000 Tables 2 and 3) |
| IS_18168_2023 | Docling formula model: math-italic, lost fractions ("…ε √R y" for "…ε/√Ry"); a split built-up column row | Normalise; canonical lines 5.5, 11.1(c), 11.2–11.4; Table 2 transcription |
| IS_18168_2023 | Table 2: a Links / closed-box cell partly illegible; the Ca / ε footnote read from a garbled row | Read both on the page image (ref p. 8) and correct the transcription |
| IS_18168_2023 | Figs 1–4 are drawings | No values |

### 7.3 Open verification items from the reference build

Close every one of these, or report it still open with its reason:

- IS 800 12.8.2.2 "(only hangers)";
- IS 801 8.1(d) P_min glyph;
- IS 811 Table 11, three cells;
- IS 808 WPB 280 X 280 X 284.13;
- IS 18168 Table 2 Links cell and Ca footnote;
- IS 875-5 8.1 h);
- IS 875-4 5.2.4 ">" [sic], confirmed on the licensed page;
- IS 875-3 10.3 g_h and M_c;
- IS 800 Table 26(a)–(d) and IS 875-3 Table 25, never transcribed;
- IS 1893 Fig. 1 and Fig. 6;
- IS 875-3 Figs 3, 5, 6, 8, the Fig. 1 full town table and the full Figs 14–15 grid;
- IS 875-4 Fig. 2;
- IS 875-4 5.2.5 and 5.2.6.

---

## 8. Rules

1. **Never invent a value.**
   - Every number, symbol and word in served text or a transcription is read from the user's PDF page, printed or rendered.
   - If you cannot read it, leave the cell blank or write `TODO(verify, pdf p. N)`, and list it in FIX_REPORT.md under "Unresolved".
   - A value computed from a printed rule (for example an s0 table from A-3, or an average) is labelled "computed from <clause>".
   - Do not fill gaps from memory, from other editions, from foreign standards or from the engines' code. The only outside data allowed is labelled reference data for figure records (town coordinates and altitudes).
2. **Quotes ≤ 15 words.** In FIX_REPORT.md, reading notes and transcriber notes, quote standard text only as a clause, table or figure id plus at most 15 words. Paraphrase anything longer and label it as yours.
3. **Provenance on every transcription.**
   - Every `*_recovered.md` starts with its source comment (page, method, date).
   - Every figure record carries the provenance line:
     `Provenance: Transcribed from IS … (licensed copy supplied by the user, pdf p. P / printed p. L), figure digitised at 300 dpi by <method>; values read from a graph — ±<x> — confirm against the licensed copy.`
   - Every canonical line names its source page.
   - Transcriber text is labelled (4.2). `[sic]` is only for misprints you saw on the image.
4. **Figure readings stay flagged:** `verify: true`, uncertainty stated, boundary towns flagged "boundary: EOR confirm".
5. **Only the user's documents.** Do not add documents or stems the user did not supply, or standard text from any other source. Do not rename stems.
6. **Keep it private.** The content is licensed to the user.
   - Do not upload PDFs, renders or corpus text to any external service. That includes online OCR and translation, paste sites, public repositories and other users.
   - Work locally, and return the output only to the user.
   - Do not keep copies after the task, beyond what your environment requires.
7. **No PDFs or images in the output**, including crops, overlays and thumbnails.
8. **Do not modify code.** Ship no `.py`. Propose code changes in FIX_REPORT.md.
9. **Never weaken a check to pass it.** Do not edit validate.py probes, do not adjust values to pass a consistency check, and do not delete a probe or a known defect to look clean.
10. **Both served files, always.** Every served-text edit goes into `<STEM>.search.md` **and** `pages_search/page_NNN.md`, identically.

---

## 9. Acceptance and FIX_REPORT.md

The job is accepted when all of these hold:

- `python scripts/validate.py --corpus` prints `CORPUS: PASS`, apart from the documented probe exceptions (6.11). If validate.py is missing, the table in 6.11 is checked by hand with `search.py`, and the result of each probe is reported.
- `strip_watermark.py --check` exits 0, and the manual grep for the licensee is empty.
- `serve_figure_transcriptions.py` prints only `OK`.
- Every item of 7.2 and 7.3 for the supplied stems is fixed or listed as unresolved with its reason.
- The zip matches 1.2 and holds no PDFs, images or code.

**FIX_REPORT.md** (plain Markdown, no licensed text beyond ids and ≤ 15-word quotes) contains:

```
# Corpus fix report — <date>
## Summary          stems supplied / missing; probes before -> after (n/n); build_stats before -> after
## Inputs           PDF file -> stem, edition read from the title page, pages, scanned/born-digital, page offset vs reference
## Changes by document and page
### <STEM>
| pdf p. | item (clause / table / figure id) | defect | fix | verified how |
## Figure transcriptions   id, method, control points / calibration, uncertainty, check-point max deviation
## Section tables          rows corrected (designation, cell, pdf p.), rows quarantined or flagged and why
## Metadata                edition, title and quality changes per stem
## Unresolved              item, pdf p., why (TODO(verify) list)
## Probe results           full validate output (PASS/FAIL per probe); exceptions with evidence
## New probes to add       (query / id, doc, short key) for each new transcription and fix
## Proposed code changes   e.g. alias groups, OVERRIDES corrections, seismic not_tabulated note
## Files the user must keep   scripts/ data files shipped in the zip (quality.json …)
```

Hand the user `corpus_fixed.zip` and `FIX_REPORT.md`. Tell them to drop the zip into the hub's IS corpus module, then run **Rebuild index** and **Validate corpus** there.
