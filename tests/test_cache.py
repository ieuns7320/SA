"""auditor.cache 단위 테스트."""

import json
import time

import pytest

from auditor import cache


@pytest.fixture(autouse=True)
def _isolate_cache_root(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path / ".cache")
    monkeypatch.setattr(cache, "TTL_SECONDS", 3600)


class TestKeyFunctions:
    def test_key_for_address_is_case_insensitive(self):
        upper = cache.key_for_address("0xABCDEF", chain_id=1)
        lower = cache.key_for_address("0xabcdef", chain_id=1)
        assert upper == lower

    def test_key_for_address_differs_by_chain_id(self):
        k1 = cache.key_for_address("0xabc", chain_id=1)
        k2 = cache.key_for_address("0xabc", chain_id=137)
        assert k1 != k2

    def test_key_for_file_depends_on_content_not_path(self, tmp_path):
        f1 = tmp_path / "a.sol"
        f2 = tmp_path / "b.sol"
        f1.write_text("contract C {}")
        f2.write_text("contract C {}")
        assert cache.key_for_file(f1) == cache.key_for_file(f2)

    def test_key_for_file_changes_with_content(self, tmp_path):
        f1 = tmp_path / "a.sol"
        f1.write_text("contract A {}")
        key_before = cache.key_for_file(f1)
        f1.write_text("contract B {}")
        key_after = cache.key_for_file(f1)
        assert key_before != key_after


class TestLoadAndStore:
    def test_miss_when_nothing_cached(self, tmp_path):
        assert cache.load("nonexistent-key", tmp_path) is None

    def test_store_then_load_round_trips_content(self, tmp_path):
        report = tmp_path / "src" / "Foo.report.md"
        report.parent.mkdir()
        report.write_text("# 리포트")
        findings = tmp_path / "src" / "Foo.findings.json"
        findings.write_text('{"findings": []}')

        cache.store("key1", report, findings, target_display="0xFoo")

        dest = tmp_path / "dest"
        loaded = cache.load("key1", dest)
        assert loaded is not None
        assert loaded.report_path.name == "Foo.report.md"
        assert loaded.report_path.read_text() == "# 리포트"
        assert loaded.findings_path.name == "Foo.findings.json"
        assert loaded.findings_path.read_text() == '{"findings": []}'

    def test_expired_entry_returns_none(self, tmp_path, monkeypatch):
        report = tmp_path / "Foo.report.md"
        report.write_text("# 리포트")
        findings = tmp_path / "Foo.findings.json"
        findings.write_text("{}")
        cache.store("key1", report, findings, target_display="0xFoo")

        monkeypatch.setattr(cache, "TTL_SECONDS", 0)
        time.sleep(0.01)
        assert cache.load("key1", tmp_path / "dest") is None

    def test_corrupted_meta_file_is_treated_as_miss(self, tmp_path):
        report = tmp_path / "Foo.report.md"
        report.write_text("# 리포트")
        findings = tmp_path / "Foo.findings.json"
        findings.write_text("{}")
        cache.store("key1", report, findings, target_display="0xFoo")

        meta_path = cache.CACHE_ROOT / "key1.meta.json"
        meta_path.write_text("not json")

        assert cache.load("key1", tmp_path / "dest") is None

    def test_missing_findings_cache_file_is_treated_as_miss(self, tmp_path):
        """
        회귀 테스트(2026-08): 이 기능(코드 뷰어) 도입 이전에 저장된 옛날 캐시
        엔트리는 findings.json이 없다 — report.md만 있다고 부분 히트로 취급하지
        않고 완전 미스로 처리해야 한다.
        """
        report = tmp_path / "Foo.report.md"
        report.write_text("# 리포트")
        findings = tmp_path / "Foo.findings.json"
        findings.write_text("{}")
        cache.store("key1", report, findings, target_display="0xFoo")

        (cache.CACHE_ROOT / "key1.findings.json").unlink()

        assert cache.load("key1", tmp_path / "dest") is None
