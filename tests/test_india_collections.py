"""NL-3: IS 18168 is in the India collection map, the corpus root resolves like steltic_india (env var, sibling
corpus folder, /workspace fallback), and the shipped JSON equals the module."""
import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from snl import india_collections as IC  # noqa: E402


def test_is18168_mapped_both_ways():
    for name in ("IS18168", "IS_18168", "engineering_standards_IS18168", "engineering_standard_IS18168"):
        assert IC.stem_for_collection(name) == "IS_18168_2023", name
    assert IC.STEM_TO_COLLECTION["IS_18168_2023"] == "engineering_standards_IS18168"
    assert IC.normalize_collection("IS_18168") == "engineering_standards_IS18168"
    assert "engineering_standards_IS18168" in IC.NL_COLLECTIONS and "engineering_standards_IS18168" in IC.DESIGN_COLLECTIONS
    assert IC.is_india_spec_collection("engineering_standards_IS18168")


def test_every_stem_has_a_collection():
    for stem in set(IC.COLLECTION_TO_STEM.values()):
        assert stem in IC.STEM_TO_COLLECTION, stem


def test_corpus_root_env_then_sibling_then_default(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIA_CORPUS_ROOT", str(tmp_path / "x"))
    assert IC.corpus_root() == str(tmp_path / "x")
    monkeypatch.delenv("INDIA_CORPUS_ROOT")
    monkeypatch.setenv("ENGINEERING_RAG_INDIA", str(tmp_path / "y"))
    assert IC.corpus_root() == str(tmp_path / "y")
    monkeypatch.delenv("ENGINEERING_RAG_INDIA")
    assert IC.corpus_root("/explicit") == "/explicit"
    # sibling corpus folder next to a copied repo
    repo = tmp_path / "steltic_nonlinear_india"
    (repo / "snl").mkdir(parents=True)
    (repo / "snl" / "india_collections.py").write_text(open(IC.__file__).read())
    sib = tmp_path / "engineering_rag_india" / "scripts"
    sib.mkdir(parents=True)
    (sib / "retrieval.py").write_text("")
    sys.path.insert(0, str(repo))
    try:
        spec = importlib.util.spec_from_file_location("ic_copy", str(repo / "snl" / "india_collections.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        assert mod.corpus_root() == str(tmp_path / "engineering_rag_india")
        (sib / "retrieval.py").unlink(); sib.rmdir()
        assert mod.corpus_root() == mod.DEFAULT_CORPUS_ROOT
    finally:
        sys.path.remove(str(repo))
    monkeypatch.setenv("RAG_ALIASES_FILE", "/a/b.json")
    assert IC.aliases_file() == "/a/b.json"


def test_json_matches_module():
    d = json.load(open(os.path.join(ROOT, "snl", "india_collection_stems.json"), encoding="utf-8"))
    assert d["collection_to_stem"] == IC.COLLECTION_TO_STEM
    assert d["stem_to_collection"] == IC.STEM_TO_COLLECTION
    assert d["nl_collections"] == IC.NL_COLLECTIONS
    assert "/workspace" not in d["corpus"].split(",")[0]
