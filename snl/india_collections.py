"""Map agent RAG collection names → India corpus document stems.

Corpus root: /workspace/engineering_rag_india (stem files under documents/standards/<STEM>/).
Hosted rag_server may register collections as engineering_standards_IS*; this map is the
canonical translation for local aliases, escalation, and docs.
"""
from __future__ import annotations

# collection alias (with or without engineering_standards_ prefix) -> stem
COLLECTION_TO_STEM: dict[str, str] = {
    # Design
    "IS800": "IS_800_2007",
    "IS_800": "IS_800_2007",
    "IS808": "IS_808_2021",
    "IS_808": "IS_808_2021",
    "IS816": "IS_816_1969",
    "IS_816": "IS_816_1969",
    "IS9595": "IS_9595_1996",
    "IS_9595": "IS_9595_1996",
    "IS4000": "IS_4000_1992",
    "IS_4000": "IS_4000_1992",
    "IS1161": "IS_1161_2014",
    "IS_1161": "IS_1161_2014",
    "IS2062": "IS_2062_Part_1_2025",
    "IS_2062": "IS_2062_Part_1_2025",
    "IS2062_P1": "IS_2062_Part_1_2025",
    # Loads — mandatory every job
    "IS875_P1": "IS_875_Part_1_2026",
    "IS875_PART1": "IS_875_Part_1_2026",
    "IS_875_P1": "IS_875_Part_1_2026",
    "IS875_P2": "IS_875_Part_2_1987",
    "IS875_PART2": "IS_875_Part_2_1987",
    "IS_875_P2": "IS_875_Part_2_1987",
    "IS875_P3": "IS_875_Part_3_2015",
    "IS875_PART3": "IS_875_Part_3_2015",
    "IS_875_P3": "IS_875_Part_3_2015",
    "IS875_P4": "IS_875_Part_4_1987",
    "IS875_PART4": "IS_875_Part_4_1987",
    "IS_875_P4": "IS_875_Part_4_1987",
    "IS875_P5": "IS_875_Part_5_1987",
    "IS875_PART5": "IS_875_Part_5_1987",
    "IS_875_P5": "IS_875_Part_5_1987",
    "IS1893": "IS_1893_Part_1_2016",
    "IS_1893": "IS_1893_Part_1_2016",
    "IS1893_P1": "IS_1893_Part_1_2016",
    "IS1893_PART1": "IS_1893_Part_1_2016",
}

# Also accept full engineering_standards_* names
for _k, _v in list(COLLECTION_TO_STEM.items()):
    COLLECTION_TO_STEM[f"engineering_standards_{_k}"] = _v

# Reverse: stem -> preferred collection name (for docs / logs)

# Dual hosted-registry prefixes (historical naming drift):
#   engineering_standards_IS*  (current India map)
#   engineering_standards_IS*  (some hosted / twin registries)
for _k, _v in list(COLLECTION_TO_STEM.items()):
    if _k.startswith("engineering_"):
        continue
    COLLECTION_TO_STEM.setdefault(f"engineering_standards_{_k}", _v)
    # Alternate spelling seen on some rag_server builds
    COLLECTION_TO_STEM.setdefault(f"engineering_standard_{_k}", _v)

STEM_TO_COLLECTION: dict[str, str] = {
    "IS_800_2007": "engineering_standards_IS800",
    "IS_808_2021": "engineering_standards_IS808",
    "IS_816_1969": "engineering_standards_IS816",
    "IS_9595_1996": "engineering_standards_IS9595",
    "IS_4000_1992": "engineering_standards_IS4000",
    "IS_1161_2014": "engineering_standards_IS1161",
    "IS_2062_Part_1_2025": "engineering_standards_IS2062",
    "IS_875_Part_1_2026": "engineering_standards_IS875_P1",
    "IS_875_Part_2_1987": "engineering_standards_IS875_P2",
    "IS_875_Part_3_2015": "engineering_standards_IS875_P3",
    "IS_875_Part_4_1987": "engineering_standards_IS875_P4",
    "IS_875_Part_5_1987": "engineering_standards_IS875_P5",
    "IS_1893_Part_1_2016": "engineering_standards_IS1893",
}

INDIA_CORPUS_ROOT = "/workspace/engineering_rag_india"
INDIA_ALIASES_FILE = f"{INDIA_CORPUS_ROOT}/indexes/aliases.json"

LOAD_COLLECTIONS = [
    "engineering_standards_IS875_P1",
    "engineering_standards_IS875_P2",
    "engineering_standards_IS875_P3",
    "engineering_standards_IS875_P4",
    "engineering_standards_IS875_P5",
    "engineering_standards_IS1893",
]

DESIGN_COLLECTIONS = [
    "engineering_standards_IS800",
    "engineering_standards_IS808",
    "engineering_standards_IS816",
    "engineering_standards_IS9595",
    "engineering_standards_IS4000",
    "engineering_standards_IS1161",
    "engineering_standards_IS2062",
]


def normalize_collection(name: str) -> str:
    """Return canonical engineering_standards_* collection name when known."""
    if not name:
        return name
    raw = str(name).strip()
    stem = stem_for_collection(raw)
    if stem and stem in STEM_TO_COLLECTION:
        return STEM_TO_COLLECTION[stem]
    return raw


def stem_for_collection(name: str) -> str | None:
    if not name:
        return None
    key = str(name).strip()
    if key in COLLECTION_TO_STEM:
        return COLLECTION_TO_STEM[key]
    # strip prefix and retry
    low = key
    if low.lower().startswith("engineering_standards_"):
        low = key[len("engineering_standards_"):]
    return COLLECTION_TO_STEM.get(low) or COLLECTION_TO_STEM.get(low.upper()) or COLLECTION_TO_STEM.get(low.replace("-", "_"))


def is_india_spec_collection(name: str) -> bool:
    c = (name or "").lower()
    if "opensees" in c or "example" in c:
        return False
    if stem_for_collection(name):
        return True
    return "engineering_standard" in c or any(
        t in c for t in ("is800", "is808", "is875", "is1893", "is816", "is4000", "is1161", "is2062", "is9595")
    )
