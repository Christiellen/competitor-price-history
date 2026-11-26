"""Testes do gerador: garantem que os problemas que o pipeline trata existem nos dados."""

from datetime import date
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from generate_data import UNMAPPED_CLASS_LABEL, generate

END = date(2026, 10, 31)


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("data")
    generate(out, days=6, end=END, seed=7)
    return out


@pytest.fixture(scope="module")
def captures(data_dir):
    return ds.dataset(data_dir / "captures", format="parquet").to_table().to_pylist()


def test_is_deterministic(tmp_path):
    assert generate(tmp_path / "a", days=2, end=END, seed=1) == generate(tmp_path / "b", days=2, end=END, seed=1)


def test_one_file_per_ingest_date(data_dir):
    for folder in (data_dir / "captures").iterdir():
        ingest = date.fromisoformat(folder.name.split("=", 1)[1])
        rows = pq.read_table(folder / "captures.parquet").to_pylist()
        assert {r["_ingest_date"] for r in rows} == {ingest}


def test_has_resends_with_corrections(captures):
    key = lambda r: (r["competitor_id"], r["origin_name"], r["destination_name"], r["departure_at"], r["service_class_label"], r["captured_at"])
    seen, corrected = {}, 0
    for r in captures:
        k = key(r)
        if k in seen and seen[k] != r["price"]:
            corrected += 1
        seen[k] = r["price"]
    assert len(seen) < len(captures)
    assert corrected > 0


def test_has_late_arrivals(captures):
    assert any(r["_ingest_date"] > r["captured_at"].date() for r in captures)


def test_sold_out_has_no_price(captures):
    sold = [r for r in captures if r["is_sold_out"]]
    assert sold
    assert all(r["price"] is None and r["seats_available"] == 0 for r in sold)
    assert all(r["price"] > 0 for r in captures if not r["is_sold_out"])


def test_never_captures_after_departure(captures):
    # captured_at está em UTC; a saída é horário local (UTC-3)
    from datetime import timedelta, timezone
    local = timezone(timedelta(hours=-3))
    assert all(r["captured_at"].astimezone(local).date() <= r["departure_at"].date() for r in captures)


def test_price_rises_close_to_departure(captures):
    """Para a nossa empresa, a média de preço com 0-2 dias deve superar a de 30+ dias."""
    from datetime import timedelta, timezone
    local = timezone(timedelta(hours=-3))
    near, far = [], []
    for r in captures:
        if r["competitor_id"] != 1 or r["price"] is None:
            continue
        days = (r["departure_at"].date() - r["captured_at"].astimezone(local).date()).days
        (near if days <= 2 else far if days >= 30 else []).append(r["price"])
    assert sum(near) / len(near) > sum(far) / len(far)


def test_spellings_differ_between_sites(captures):
    names = {r["origin_name"] for r in captures if "PAULO" in r["origin_name"].upper()}
    assert len(names) >= 3


def test_noise_exists(data_dir, captures):
    aliases = pq.read_table(data_dir / "dimensions" / "locality_aliases.parquet").to_pylist()
    known = {(a["competitor_id"], a["raw_name"]) for a in aliases}
    assert any((r["competitor_id"], r["origin_name"]) not in known for r in captures)
    assert any(r["service_class_label"] == UNMAPPED_CLASS_LABEL for r in captures)
