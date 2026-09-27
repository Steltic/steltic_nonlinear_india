"""The Review agent is told HOW to query the IS corpus: contract/QUERYING_IS_CORPUS.md (the same file ships in
steltic_india and steltic_CFS_india) is in its prompt, and the tool accepts the stems the file uses."""
from snl import rag, review, standards


def test_the_review_prompt_carries_the_query_instructions():
    assert "HOW TO QUERY THE IS CORPUS" in review.SYSTEM and "[missing contract/QUERYING_IS_CORPUS.md" not in review.SYSTEM
    for must in ("Table 9(a)", "not_tabulated", "context_neighbors", "section 9", "RETRIEVAL POLICY"):
        assert must in review.SYSTEM, must


def test_the_tool_takes_the_short_key_or_the_stem():
    enum = standards.TOOLS[0]["function"]["parameters"]["properties"]["document"]["enum"]
    for k in rag.DOCUMENTS:
        assert k in enum and rag.STEMS[k] in enum
        assert rag.resolve(rag.STEMS[k]) == k


def test_no_usa_query_skill_is_the_india_retrieval_rule():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    boot = (root / "prompts" / "bootstrap_prompts.md").read_text(encoding="utf-8")
    assert "contract/QUERYING_IS_CORPUS.md" in boot
    start = (root / "contract" / "INDIA_START.md").read_text(encoding="utf-8")
    assert "QUERYING_IS_CORPUS.md" in start and "Query file manager" not in start
