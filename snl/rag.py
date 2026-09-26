"""rag.py -- the standards search the Review step grounds its clauses with (stdlib only).

Same wire contract as HR Steel's search tool: POST RAG_API_URL {"query", "collection", "top_k", "clause",
"chapter"} -> {"results": [{"text", "source", "section", "title", "page", "score", "authoritative"}], "note"}.
India fork: RAG_API_URL is the IS corpus bridge (engineering_rag_india's rag_server.py, started by the hub for
the run as {server.engineering_rag_india}/query; standalone, the corpus's own scripts/serve_http.py). Only IS
documents are searched (owner ruling D3: IS standards only, no foreign design basis); the collection names are
the engineering_standards_IS* names of snl/india_collections.py. Never point this at the US corpus.
Empty RAG_API_URL -> search() says so and the review goes on from the model's own knowledge, flagged.
"""
from __future__ import annotations
import json, os, time, urllib.error, urllib.request

# what the model may name in `document`; the collection is the engineering_standards_IS* name the India corpus
# bridge and steltic_india's search tool use (snl/india_collections.py STEM_TO_COLLECTION)
DOCUMENTS = {
    "IS1893": ("engineering_standards_IS1893", "IS 1893 (Part 1):2016 + Amd 1-2 earthquake resistant design (6.4.2 spectrum and Sa/g, Table 3 Z, Table 8 I, 7.2.4 damping, 7.7.4 time history, 7.11.1 storey drift)"),
    "IS800": ("engineering_standards_IS800", "IS 800:2007 general construction in steel (member strength, Table 4 load combinations, Section 12 seismic design: 12.7-12.11 joint-rotation capacities)"),
    "IS18168": ("engineering_standards_IS18168", "IS 18168:2023 design and detailing of steel buildings for earthquake resistance (Table 1 Ry / Ru, overstrength, capacity design)"),
    "IS2062": ("engineering_standards_IS2062", "IS 2062 (Part 1):2025 hot rolled structural steel (Table 3 mechanical properties: fy / fu by grade and thickness)"),
    "IS808": ("engineering_standards_IS808", "IS 808:2021 hot rolled steel sections (dimensions and properties)"),
    "IS875_P1": ("engineering_standards_IS875_P1", "IS 875 (Part 1) dead loads"),
    "IS875_P2": ("engineering_standards_IS875_P2", "IS 875 (Part 2):1987 imposed loads"),
}


def url() -> str:
    return (os.environ.get("RAG_API_URL") or "").strip()


def configured() -> bool:
    return bool(url())


def search(query: str, document: str = "IS1893", top_k: int = 5, clause: str = "", chapter: str = "", timeout: float = 60.0) -> dict:
    """One search. -> {"ok", "results": [...], "note", "collection", "ms"}; never raises."""
    t0 = time.time()
    doc = (document or "IS1893").strip().upper().replace("-", "").replace("_", "")
    coll = None
    for key, (c, _d) in DOCUMENTS.items():
        if doc == key.replace("_", "") or doc == c.upper().replace("_", ""):
            coll = c
    if coll is None:
        if document and document.lower().startswith("engineering_standards"):
            coll = document
        else:
            return {"ok": False, "results": [], "collection": document,
                    "note": "unknown document %r -- use one of %s" % (document, ", ".join(DOCUMENTS)), "ms": 0}
    if not url():
        return {"ok": False, "results": [], "collection": coll, "ms": 0,
                "note": "no standards server (RAG_API_URL is empty): cite from memory and mark the clause UNVERIFIED"}
    payload = {"query": query, "collection": coll, "top_k": max(1, min(int(top_k or 5), 8))}
    if clause:
        payload["clause"] = clause
    if chapter:
        payload["chapter"] = chapter
    body = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    tok = os.environ.get("RAG_API_TOKEN")
    if tok:
        hdrs["Authorization"] = "Bearer " + tok
    last = None
    for _ in range(2):
        try:
            req = urllib.request.Request(url(), data=body, headers=hdrs, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            if not isinstance(data, dict):
                data = {"results": data}
            res = []
            for h in (data.get("results") or [])[:payload["top_k"]]:
                if not isinstance(h, dict):
                    continue
                res.append({"text": str(h.get("text") or h.get("snippet") or "")[:2500], "source": str(h.get("source") or h.get("doc") or coll),
                            "section": str(h.get("section") or h.get("section_id") or ""), "title": str(h.get("title") or ""),
                            "page": h.get("page") or h.get("printed_label") or h.get("pdf_page"), "score": h.get("score"),
                            "authoritative": bool(h.get("authoritative"))})
            return {"ok": True, "results": res, "collection": coll, "note": data.get("note") or "", "matched": data.get("matched"),
                    "ms": int((time.time() - t0) * 1000)}
        except Exception as e:                                   # noqa: BLE001
            last = e
    return {"ok": False, "results": [], "collection": coll, "ms": int((time.time() - t0) * 1000),
            "note": "standards server unreachable (%s): cite from memory and mark the clause UNVERIFIED" % last}


def render(result: dict) -> str:
    """The tool result as the model reads it."""
    if not result.get("results"):
        return "NO PASSAGES. " + (result.get("note") or "")
    out = []
    for i, h in enumerate(result["results"], 1):
        head = " ".join(x for x in (h.get("source"), h.get("section"), ("p. %s" % h["page"]) if h.get("page") else "") if x)
        out.append("[%d] %s%s\n%s" % (i, head, (" -- " + h["title"]) if h.get("title") else "", h["text"]))
    if result.get("note"):
        out.append("note: " + result["note"])
    return "\n\n".join(out)
