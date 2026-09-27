"""standards.py -- what every SNL agent shares when it asks the IS corpus: the retrieval policy and the tool.

The policy is the IS corpus bridge's (the hub's IS corpus module rag_server: `type`, `query`, `clause`,
`context_neighbors`), the one HR Steel's (steltic_india) search tool follows: ONE IS document per call, an
EXACT id when the provision is known, full text only to navigate to an id. The tool applies it to whatever
the model sends (snl/rag.py policy_plan) and records the form it sent. `review` writes the engineer's review
with it; `collect` fetches its tables with the same exact lookups.
India (owner ruling D3): IS standards only, no foreign design basis.
"""
from __future__ import annotations

from . import rag

RETRIEVAL_POLICY = """===== RETRIEVAL POLICY (mandatory -- how every search_engineering_standards call is written) =====
This is the query policy the IS corpus bridge is built for (the hub's IS corpus module rag_server: `type`,
`query`, `clause`, `context_neighbors`), the same policy HR Steel's (steltic_india) search tool follows. The
tool applies it to whatever you send and records the form it sent; write it that way yourself.

1. ONE document per call, by its key: document="IS1893" | "IS800" | "IS18168" | "IS2062" | "IS808" | "IS875_P1" | "IS875_P2".
   Never search all documents blindly. System -> component -> action -> method -> the one document that
   governs: the spectrum (6.4.2), Z (Table 3), I (Table 8), damping (7.2.4), the time history method (7.7.4)
   and the storey-drift clause (7.11.1) are IS 1893 (Part 1):2016; member strength, load combinations
   (Table 4) and the Section 12 joint-rotation capacities are IS 800:2007; Ry / Ru and capacity design for
   earthquake resistance are IS 18168:2023; fy / fu are IS 2062 (Part 1):2025 Table 3; section properties
   are IS 808:2021. There is no foreign design basis: no ASCE / AISC document is searched or cited.
2. EXACT ID WHEN KNOWN. type="exact_section" | "exact_table", query = the id ALONE:
     {"type":"exact_section","document":"IS1893","query":"7.11.1.1","purpose":"storey drift (linear analysis, for comparison)"}
     {"type":"exact_table","document":"IS1893","query":"Table 3","purpose":"zone factor Z"}
     {"type":"exact_section","document":"IS800","query":"12.8.1","purpose":"SCBF joint-rotation capacity (reference only)"}
   Not a sentence. Not the document name. Not "IS 1893 (Part 1):2016 clause 7.11.1.1 on storey drift".
3. FULL TEXT ONLY TO NAVIGATE: type="fts", query = the standard's own printed words, one idea, no
   sentence, no ids mixed in ("storey drift 0.004 times the storey height", not "what drift does IS 1893
   allow"). Read the ids it returns, then ask for them EXACTLY in the next call.
4. One provision per call: provision, definition, expression, limits, table, procedure -- each its own
   call. For every expression you compute from, also fetch its "where:" variables (context_neighbors=1),
   its applicability and its exceptions.
5. Waves: (1) navigation + the core provisions -> (2) definitions, limits and the cross-references the
   results name -> (3) verification of every factor that entered a number you quote.
6. BIS documents carry no separate commentary: want_commentary stays false, and a commentary or foreword
   excerpt never supplies a design value.
7. Search only the documents listed under DOCUMENTS IN THE CORPUS. A document listed as ABSENT is not in
   the IS corpus on this PC: do not search it (such a call is answered with a corpus-gap note, is not
   counted, and is wasted); cite it from memory, marked (UNVERIFIED), and say in section 8 that it was
   unavailable.
8. A miss is escalated for you: the exact id, the clause/chapter filter dropped, a reworded query, then
   every other IS document. When the result says another document answered, cite THAT document, not the
   one you asked for.
9. Never invent an id. NO PASSAGES after the ladder is an honest answer: re-word ONCE in the standard's own
   terms or ask for the parent clause; do not fill the gap from memory without marking it (UNVERIFIED).
   Every clause you cite as verified comes from a passage returned this session -- cite document, clause,
   table id and the printed page the passage gives.
10. Search as often as the review needs. There is no reward for searching less; an uncited clause you
   could have looked up is the failure, not an extra call.
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_engineering_standards",
        "description": ("Search the licensed IS corpus for the clause or table you are about to cite. "
                        "ONE provision, ONE document per call. When you know the id, ask for it EXACTLY: type=\"exact_section\" | "
                        "\"exact_table\" with `query` = the id alone (\"7.11.1.1\", \"12.8.1\", \"Table 3\") -- not a sentence, not the "
                        "document name. Use type=\"fts\" only to NAVIGATE to an id, with `query` in the standard's own printed words, one "
                        "idea, no ids mixed in; read the ids it returns and ask for them exactly next. Search only documents the corpus "
                        "holds (see DOCUMENTS IN THE CORPUS). A miss is escalated for you (exact id, filters dropped, reworded, other IS "
                        "documents) and the result says which document answered. Cite only what a passage supports; a clause the "
                        "search cannot find is cited from memory and marked (UNVERIFIED). There is no foreign design basis: do not cite "
                        "ASCE / AISC as authority."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The id alone for an exact type; otherwise the standard's own printed words, one idea"},
                "document": {"type": "string", "enum": list(rag.DOCUMENTS), "description": "; ".join("%s = %s" % (k, d) for k, (_c, d) in rag.DOCUMENTS.items())},
                "type": {"type": "string", "enum": ["exact_section", "exact_equation", "exact_table", "id", "fts", "keyword"],
                         "description": "How to look it up. Exact types take the id alone in `query`. fts/keyword navigate."},
                "clause": {"type": "string", "description": "Exact clause / table id, when you did not put it in `query`"},
                "chapter": {"type": "string", "description": "Restrict a navigation query to one section of the standard, e.g. 7 or 12"},
                "purpose": {"type": "string", "description": "Why you need it, short -- recorded in the transcript"},
                "want_commentary": {"type": "boolean", "description": "Commentary instead of the provision. Default false; BIS documents carry no separate commentary, and commentary never supplies a design value."},
                "context_neighbors": {"type": "integer", "minimum": 0, "maximum": 2,
                                      "description": "Surrounding chunks to include. Use 1 for an expression, to get its \"where:\" variables."},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query", "document"],
        },
    },
}]
