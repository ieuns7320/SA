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

    def test_expired_entry_is_deleted_from_disk(self, tmp_path, monkeypatch):
        """
        회귀 테스트(2026-08): 예전엔 load()가 만료된 엔트리를 미스로만 취급하고
        파일은 CACHE_ROOT에 그대로 남겨뒀다 — 재조회되지 않는 키는 디스크를
        영원히 잡아먹었다. 이제 만료 판정 시 그 자리에서 지운다.
        """
        report = tmp_path / "Foo.report.md"
        report.write_text("# 리포트")
        findings = tmp_path / "Foo.findings.json"
        findings.write_text("{}")
        cache.store("key1", report, findings, target_display="0xFoo")

        monkeypatch.setattr(cache, "TTL_SECONDS", 0)
        time.sleep(0.01)
        cache.load("key1", tmp_path / "dest")

        assert not (cache.CACHE_ROOT / "key1.meta.json").exists()
        assert not (cache.CACHE_ROOT / "key1.report.md").exists()
        assert not (cache.CACHE_ROOT / "key1.findings.json").exists()

    def test_corrupted_meta_file_is_treated_as_miss(self, tmp_path):
        report = tmp_path / "Foo.report.md"
        report.write_text("# 리포트")
        findings = tmp_path / "Foo.findings.json"
        findings.write_text("{}")
        cache.store("key1", report, findings, target_display="0xFoo")

        meta_path = cache.CACHE_ROOT / "key1.meta.json"
        meta_path.write_text("not json")

        assert cache.load("key1", tmp_path / "dest") is None
        assert not meta_path.exists()

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


class TestSweepExpired:
    def _store(self, tmp_path, key: str) -> None:
        report = tmp_path / f"{key}.report.md"
        report.write_text("# 리포트")
        findings = tmp_path / f"{key}.findings.json"
        findings.write_text("{}")
        cache.store(key, report, findings, target_display=key)

    def test_no_cache_root_returns_zero(self, tmp_path):
        assert cache.sweep_expired() == 0

    def test_removes_only_expired_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, "TTL_SECONDS", 100)
        fake_now = [1000.0]
        monkeypatch.setattr(cache.time, "time", lambda: fake_now[0])

        self._store(tmp_path, "old")  # cached_at = 1000

        fake_now[0] = 1150  # 150초 후 — TTL(100초)을 넘김
        self._store(tmp_path, "fresh")  # cached_at = 1150, 아직 안 만료

        removed = cache.sweep_expired()

        assert removed == 1
        assert not (cache.CACHE_ROOT / "old.meta.json").exists()
        assert (cache.CACHE_ROOT / "fresh.meta.json").exists()

    def test_removes_corrupted_meta_entries(self, tmp_path):
        self._store(tmp_path, "broken")
        (cache.CACHE_ROOT / "broken.meta.json").write_text("not json")

        removed = cache.sweep_expired()

        assert removed == 1
        assert not (cache.CACHE_ROOT / "broken.meta.json").exists()
