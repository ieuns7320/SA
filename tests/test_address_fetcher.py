"""auditor.input.address_fetcher 단위 테스트.

실제 Etherscan API를 호출하지 않고 requests.get을 모킹해서 응답 처리 로직만
검증한다. 재시도 테스트는 auditor.input.address_fetcher.time.sleep을 no-op으로
바꿔서 실제로 기다리지 않는다.
"""

import json

import pytest
import requests

from auditor.input.address_fetcher import fetch_verified_source


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _no_sleep(monkeypatch):
    monkeypatch.setattr("auditor.input.address_fetcher.time.sleep", lambda s: None)


def test_missing_api_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("ETHERSCAN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ETHERSCAN_API_KEY"):
        fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key=None)


def test_unverified_contract_raises(monkeypatch, tmp_path):
    payload = {"status": "1", "result": [{"SourceCode": "", "ContractName": "X"}]}
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
    with pytest.raises(RuntimeError, match="검증되지 않았습니다"):
        fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")


def test_api_error_status_raises(monkeypatch, tmp_path):
    payload = {"status": "0", "message": "NOTOK", "result": "Invalid address format"}
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
    with pytest.raises(RuntimeError):
        fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")


def test_single_file_source_is_saved(monkeypatch, tmp_path):
    payload = {
        "status": "1",
        "result": [{"SourceCode": "contract X {}", "ContractName": "X"}],
    }
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
    path = fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")
    assert path.name == "X.sol"
    assert path.read_text() == "contract X {}"


def test_multi_file_standard_json_input_saves_all_and_finds_entry(monkeypatch, tmp_path):
    sources = {
        "contracts/Interface.sol": {"content": "interface I {}"},
        "contracts/Main.sol": {"content": "contract Main is I {}"},
    }
    source_code = json.dumps({"sources": sources})
    payload = {
        "status": "1",
        "result": [{"SourceCode": source_code, "ContractName": "Main"}],
    }
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
    entry = fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")

    assert entry.name == "Main.sol"
    assert entry.exists()
    assert (tmp_path / "Main" / "contracts" / "Interface.sol").exists()
    assert (tmp_path / "Main" / "contracts" / "Main.sol").exists()


def test_double_brace_wrapped_json_is_unwrapped(monkeypatch, tmp_path):
    """Etherscan은 standard-json-input을 이중 중괄호로 감싸서 내려줄 때가 있다."""
    sources = {"Main.sol": {"content": "contract Main {}"}}
    wrapped = "{" + json.dumps({"sources": sources}) + "}"
    assert wrapped.startswith("{{") and wrapped.endswith("}}")
    payload = {
        "status": "1",
        "result": [{"SourceCode": wrapped, "ContractName": "Main"}],
    }
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
    entry = fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")
    assert entry.exists()
    assert "contract Main" in entry.read_text()


class TestProxyResolution:
    def test_proxy_resolves_to_implementation_contract(self, monkeypatch, tmp_path):
        """
        프록시 주소를 넣으면 delegatecall 껍데기가 아니라 Etherscan이 알려주는
        구현(Implementation) 컨트랙트의 소스를 대신 받아와야 한다.
        """
        proxy_addr = "0x" + "1" * 40
        impl_addr = "0x" + "2" * 40

        proxy_payload = {
            "status": "1",
            "result": [
                {
                    "SourceCode": "contract Proxy {}",
                    "ContractName": "Proxy",
                    "Proxy": "1",
                    "Implementation": impl_addr,
                }
            ],
        }
        impl_payload = {
            "status": "1",
            "result": [
                {
                    "SourceCode": "contract RealLogic { function withdraw() external {} }",
                    "ContractName": "RealLogic",
                    "Proxy": "0",
                    "Implementation": "",
                }
            ],
        }

        def fake_get(url, params, timeout):
            payload = proxy_payload if params["address"] == proxy_addr else impl_payload
            return FakeResponse(payload)

        monkeypatch.setattr("requests.get", fake_get)
        path = fetch_verified_source(proxy_addr, output_dir=str(tmp_path), api_key="k")

        assert path.name == "RealLogic.sol"
        assert "withdraw" in path.read_text()

    def test_non_proxy_or_missing_implementation_is_analyzed_directly(self, monkeypatch, tmp_path):
        payload = {
            "status": "1",
            "result": [
                {
                    "SourceCode": "contract Weird {}",
                    "ContractName": "Weird",
                    "Proxy": "0",
                    "Implementation": "",
                }
            ],
        }
        monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
        path = fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")
        assert path.name == "Weird.sol"


class TestRetries:
    def test_network_error_retries_then_succeeds(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)
        payload = {
            "status": "1",
            "result": [{"SourceCode": "contract X {}", "ContractName": "X"}],
        }
        calls = {"n": 0}

        def flaky_get(*a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise requests.exceptions.ConnectionError("boom")
            return FakeResponse(payload)

        monkeypatch.setattr("requests.get", flaky_get)
        path = fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")
        assert path.name == "X.sol"
        assert calls["n"] == 3

    def test_network_error_persists_raises_clear_error(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)

        def always_fail(*a, **k):
            raise requests.exceptions.Timeout("timed out")

        monkeypatch.setattr("requests.get", always_fail)
        with pytest.raises(RuntimeError, match="네트워크 오류"):
            fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")

    def test_rate_limit_retries_then_succeeds(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)
        rate_limited = {"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
        success = {
            "status": "1",
            "result": [{"SourceCode": "contract X {}", "ContractName": "X"}],
        }
        calls = {"n": 0}

        def flaky_get(*a, **k):
            calls["n"] += 1
            return FakeResponse(rate_limited if calls["n"] < 2 else success)

        monkeypatch.setattr("requests.get", flaky_get)
        path = fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")
        assert path.name == "X.sol"
        assert calls["n"] == 2

    def test_persistent_rate_limit_raises_clear_error(self, monkeypatch, tmp_path):
        _no_sleep(monkeypatch)
        payload = {"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
        monkeypatch.setattr("requests.get", lambda *a, **k: FakeResponse(payload))
        with pytest.raises(RuntimeError, match="레이트리밋"):
            fetch_verified_source("0xabc", output_dir=str(tmp_path), api_key="k")
