"""Тесты пост-обработки ответа модели."""
from __future__ import annotations

import pytest

from llm.postprocess import PostProcessError, postprocess


def test_strips_whitespace_and_code_fences():
    raw = "```\n  Привет   мир \n```"
    assert postprocess(raw) == "Привет мир"


def test_extracts_json_summary():
    raw = '{"summary": "Краткое резюме текста."}'
    assert postprocess(raw) == "Краткое резюме текста."


def test_json_fence_is_parsed():
    raw = '```json\n{"answer": "Ответ из JSON"}\n```'
    assert postprocess(raw) == "Ответ из JSON"


def test_invalid_json_falls_back_to_cleaned_text():
    raw = '{"summary": "незакрытая строка'
    result = postprocess(raw)
    assert result.startswith('{"summary"')


def test_empty_response_raises():
    with pytest.raises(PostProcessError):
        postprocess("   ")


def test_none_response_raises():
    with pytest.raises(PostProcessError):
        postprocess(None)
