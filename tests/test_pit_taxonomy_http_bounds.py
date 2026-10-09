"""官方分類來源的慢速串流不能越過完整回應時限。"""
from io import BytesIO
import pytest
from data_module import pit_taxonomy_source_producer as producer


def test_complete_stream_preserves_exact_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(producer, "monotonic_ns", lambda: 1)
    raw = b"official bytes" * 10000
    assert producer._read_bounded_taxonomy_http_body(BytesIO(raw), started_ns=0) == raw


def test_oversized_stream_keeps_one_over_limit_for_custody_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(producer, "monotonic_ns", lambda: 1)
    monkeypatch.setattr(producer, "PIT_TAXONOMY_MAX_SOURCE_BYTES", 8)
    assert producer._read_bounded_taxonomy_http_body(BytesIO(b"0123456789"), started_ns=0) == b"012345678"


def test_slow_stream_cannot_reset_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0, 450_000_000_000, 450_000_000_001, 900_000_000_000])
    monkeypatch.setattr(producer, "monotonic_ns", lambda: next(clock))
    class SlowStream:
        calls = 0
        def read1(self, size: int) -> bytes:
            self.calls += 1
            return b"x"
    response = SlowStream()
    with pytest.raises(producer.PITTaxonomySourceError, match="total read timeout"):
        producer._read_bounded_taxonomy_http_body(response, started_ns=0)
    assert response.calls == 2


def test_nonstreaming_response_fails_closed() -> None:
    with pytest.raises(producer.PITTaxonomySourceError, match="bounded streaming reader"):
        producer._read_bounded_taxonomy_http_body(object(), started_ns=0)
