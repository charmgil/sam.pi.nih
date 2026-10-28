"""Catalog defaults: pi's startup model is set once, never over a model the user saved."""

import json

from samkit import llm


def test_catalog_defaults_resolve_to_variants():
    cat = llm.load_catalog()
    assert llm.default_variant(cat, "agent") == "sam-gemma4-31b"
    assert llm.default_variant(cat, "consultant") == "sam-gemma4-31b"


def test_startup_model_written_when_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    llm.set_startup_model(llm.load_catalog(), {"sam-gemma4-31b"})
    s = json.loads((tmp_path / "settings.json").read_text())
    assert (s["defaultProvider"], s["defaultModel"]) == ("ollama", "sam-gemma4-31b")


def test_saved_choice_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    saved = {"defaultProvider": "ollama", "defaultModel": "sam-qwen3.8-27b", "theme": "dark"}
    (tmp_path / "settings.json").write_text(json.dumps(saved))
    llm.set_startup_model(llm.load_catalog(), {"sam-gemma4-31b"})
    assert json.loads((tmp_path / "settings.json").read_text()) == saved


def test_nothing_written_before_the_model_is_pulled(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    llm.set_startup_model(llm.load_catalog(), set())
    assert not (tmp_path / "settings.json").exists()
