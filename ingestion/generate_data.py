"""Gera dados sintéticos de capturas de tarifas de ônibus rodoviário.

Cenário: uma viação ("Nossa Viação") monitora as tarifas dos concorrentes nas
mesmas rotas. Todo dia o scraper consulta, para cada rota, as saídas dos
próximos dias (antecedência de 0 a 30 dias, mais 45 e 60) e grava o preço de
cada classe de serviço, os assentos disponíveis e se a saída está esgotada.

Saída (Parquet):
    <out>/dimensions/competitors.parquet       concorrentes (inclui a nossa empresa)
    <out>/dimensions/localities.parquet        cidades com código IBGE
    <out>/dimensions/routes.parquet            nossas rotas (origem e destino)
    <out>/dimensions/locality_aliases.parquet  grafia de cada cidade em cada site
    <out>/captures/ingest_date=AAAA-MM-DD/captures.parquet

Problemas reproduzidos de propósito:
- cada site escreve a cidade e a classe de um jeito ("SAO PAULO (TIETE)/SP",
  "São Paulo - SP", "SEMI-LEITO", "Semi Leito");
- reenvios da mesma captura, às vezes com preço corrigido;
- chegadas atrasadas (ingeridas 1 a 3 dias depois);
- saídas esgotadas (sem preço) e rotas fora da nossa malha;
- um rótulo de classe que não existe no nosso mapeamento.

Preço: tarifa base pela distância e pela classe, ajustada pela antecedência
(mais caro perto da saída), pelo dia da semana, por feriados e pela demanda de
cada saída. Um dos concorrentes pratica preço fixo, sem precificação dinâmica.

Uso:
    python generate_data.py --out ../data --days 180

Com os valores padrão: cerca de 2,5 milhões de capturas.
"""

from __future__ import annotations

import argparse
import random
import unicodedata
import zlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Brasília (sem horário de verão): UTC-3
LOCAL_TZ = timezone(timedelta(hours=-3))

LOCALITIES = [
    # id, cidade, UF, código IBGE
    (1, "São Paulo", "SP", 3550308),
    (2, "Rio de Janeiro", "RJ", 3304557),
    (3, "Belo Horizonte", "MG", 3106200),
    (4, "Curitiba", "PR", 4106902),
    (5, "Campinas", "SP", 3509502),
    (6, "Ribeirão Preto", "SP", 3543402),
    (7, "Londrina", "PR", 4113700),
    (8, "Uberlândia", "MG", 3170206),
    (9, "Goiânia", "GO", 5208707),
    (10, "Brasília", "DF", 5300108),
    (11, "Florianópolis", "SC", 4205407),
    (12, "Campo Grande", "MS", 5002704),
]
TERMINALS = {1: "TIETE", 2: "NOVO RIO", 3: "GOVERNADOR ISRAEL PINHEIRO"}

# pares de cidades atendidos, com distância rodoviária aproximada (km)
ROUTE_PAIRS = [
    (1, 2, 430), (1, 3, 586), (1, 4, 408), (1, 5, 95), (1, 6, 315), (4, 11, 300),
    (3, 10, 740), (9, 10, 210), (7, 1, 540), (8, 9, 340), (12, 1, 1014), (6, 3, 520),
]
# cidades fora da nossa malha que aparecem nos sites (ruído)
OUTSIDE = ["SOROCABA/SP", "Bauru - SP", "Joinville", "VITORIA/ES"]

COMPETITORS = [
    # id, nome, canal, é a nossa empresa, nível de preço, faz precificação dinâmica
    (1, "Nossa Viação", "site próprio", True, 0.00, True),
    (2, "Viação Alfa", "site próprio", False, -0.06, True),
    (3, "Expresso Beta", "marketplace", False, 0.04, True),
    (4, "Transportes Gama", "site próprio", False, -0.02, True),
    (5, "Viação Delta", "marketplace", False, 0.08, False),
]

CLASSES = {
    # código: (multiplicador da tarifa, assentos, rótulos usados pelos sites)
    "CONV": (1.00, 46, ["Convencional", "CONVENCIONAL", "Conv."]),
    "EXEC": (1.20, 44, ["Executivo", "EXECUTIVO", "Exec."]),
    "SEMI": (1.45, 42, ["Semi-Leito", "SEMILEITO", "Semi Leito"]),
    "LEITO": (1.90, 28, ["Leito", "LEITO CAMA", "Leito-Cama"]),
}
UNMAPPED_CLASS_LABEL = "Leito Cama Premium"

ANTECEDENCE_DAYS = list(range(0, 31)) + [45, 60]
HOLIDAYS = [date(2026, m, d) for m, d in [(1, 1), (2, 16), (2, 17), (4, 3), (4, 21), (5, 1), (6, 4),
                                          (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]]
HOLIDAYS += [date(2025, m, d) for m, d in [(9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)]]

CAPTURE_SCHEMA = pa.schema(
    [
        ("competitor_id", pa.int64()),
        ("origin_name", pa.string()),
        ("destination_name", pa.string()),
        ("departure_at", pa.timestamp("us")),          # horário local da saída, sem fuso
        ("service_class_label", pa.string()),
        ("price", pa.float64()),                       # nulo quando esgotado
        ("seats_available", pa.int64()),
        ("is_sold_out", pa.bool_()),
        ("captured_at", pa.timestamp("us", tz="UTC")),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
        ("_ingest_date", pa.date32()),
        ("source_file", pa.string()),
    ]
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def spell(style: int, loc_id: int) -> str:
    """Grafia da cidade em cada site."""
    _, city, uf, _ = LOCALITIES[loc_id - 1]
    if style == 0:
        return f"{city} - {uf}"
    if style == 1:
        terminal = f" ({TERMINALS[loc_id]})" if loc_id in TERMINALS else ""
        return f"{strip_accents(city).upper()}{terminal}/{uf}"
    if style == 2:
        return city
    return f"{strip_accents(city).upper()} - {uf}"


def stable_random(*key) -> random.Random:
    """Gerador reprodutível por chave: a mesma saída tem sempre a mesma demanda."""
    return random.Random(zlib.crc32("|".join(map(str, key)).encode()))


def round_fare(value: float) -> float:
    """Tarifas terminam em ,90."""
    return max(9.90, int(value) + 0.90)


def antecedence_curve(days: int) -> float:
    if days >= 30:
        return 0.78
    if days >= 21:
        return 0.85
    if days >= 14:
        return 0.92
    if days >= 7:
        return 1.00
    if days >= 3:
        return 1.12
    if days >= 1:
        return 1.25
    return 1.35


def day_factor(day: date) -> float:
    factor = {4: 1.22, 6: 1.18, 0: 1.05, 5: 0.95}.get(day.weekday(), 1.0)
    if any(abs((day - h).days) <= 1 for h in HOLIDAYS):
        factor *= 1.30
    return factor


@dataclass(frozen=True)
class Service:
    """Uma saída regular: concorrente, rota, horário e classe."""

    competitor_id: int
    origin_id: int
    destination_id: int
    distance: int
    departure_time: time
    class_code: str
    class_label: str


def build_services(rng: random.Random) -> list[Service]:
    services = []
    for cid, _, _, is_own, _, _ in COMPETITORS:
        for a, b, km in ROUTE_PAIRS:
            for origin, dest in ((a, b), (b, a)):
                if not is_own and rng.random() > 0.6:  # cada concorrente atende parte das rotas
                    continue
                n_departures = rng.randint(2, 5)
                slots = sorted(rng.sample(range(12, 48), n_departures))  # 06:00 a 23:30
                for slot in slots:
                    dep_time = time(slot // 2, 30 * (slot % 2))
                    night = dep_time.hour >= 20 or dep_time.hour < 2
                    pool = ["SEMI", "LEITO"] if night and km > 300 else ["CONV", "EXEC", "SEMI"]
                    for code in rng.sample(pool, k=rng.choice([1, 1, 2])):
                        label = CLASSES[code][2][cid % len(CLASSES[code][2])]
                        if code == "LEITO" and cid == 3 and rng.random() < 0.3:
                            label = UNMAPPED_CLASS_LABEL
                        services.append(Service(cid, origin, dest, km, dep_time, code, label))
    return services


def fare_and_seats(svc: Service, departure_day: date, antecedence: int, level: float, dynamic: bool):
    """Preço e ocupação de uma saída numa antecedência. Reprodutível por saída."""
    r = stable_random(svc.competitor_id, svc.origin_id, svc.destination_id, departure_day, svc.departure_time, svc.class_code)
    demand = day_factor(departure_day) * r.uniform(0.85, 1.20)
    if svc.departure_time.hour in (6, 7, 18, 19, 22, 23):
        demand *= 1.08
    promo = r.random() < 0.06 and antecedence >= 7

    mult, seats, _ = CLASSES[svc.class_code]
    base = (12 + 0.21 * svc.distance) * mult * (1 + level)
    curve = antecedence_curve(antecedence) if dynamic else 1.0
    price = round_fare(base * curve * (demand if dynamic else 1.0) * (0.85 if promo else 1.0))

    occupancy = (0.18 + 0.64 * (1 - min(antecedence, 30) / 30)) * demand * r.uniform(0.9, 1.1)
    available = max(0, round(seats * (1 - occupancy)))
    return price, available


def write_table(rows: list[dict], path: Path, schema: pa.Schema | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="snappy")


def write_dimensions(out: Path, rng: random.Random) -> list[dict]:
    write_table(
        [{"competitor_id": c[0], "competitor_name": c[1], "channel": c[2], "is_own_company": c[3]} for c in COMPETITORS],
        out / "dimensions" / "competitors.parquet",
    )
    write_table(
        [{"locality_id": i, "city": c, "state": uf, "ibge_code": ibge} for i, c, uf, ibge in LOCALITIES],
        out / "dimensions" / "localities.parquet",
    )
    routes, rid = [], 0
    for a, b, km in ROUTE_PAIRS:
        for origin, dest in ((a, b), (b, a)):
            rid += 1
            routes.append({"route_id": rid, "origin_locality_id": origin, "destination_locality_id": dest, "distance_km": km})
    write_table(routes, out / "dimensions" / "routes.parquet")

    aliases = [
        {"competitor_id": cid, "raw_name": spell(cid % 4, loc_id), "locality_id": loc_id}
        for cid, *_ in COMPETITORS
        for loc_id, *_ in LOCALITIES
    ]
    write_table(aliases, out / "dimensions" / "locality_aliases.parquet")
    return routes


def generate(out: Path, days: int, end: date, seed: int) -> dict:
    rng = random.Random(seed)
    start = end - timedelta(days=days - 1)
    write_dimensions(out, rng)
    services = build_services(rng)
    level = {c[0]: c[4] for c in COMPETITORS}
    dynamic = {c[0]: c[5] for c in COMPETITORS}

    buffers: dict[date, list[dict]] = defaultdict(list)
    stats = {"rows": 0, "files": 0, "duplicates": 0, "late": 0, "sold_out": 0, "outside": 0}

    def flush(ingest_day: date) -> None:
        rows = buffers.pop(ingest_day, [])
        if not rows:
            return
        rows.sort(key=lambda r: (r["competitor_id"], r["captured_at"]))
        write_table(rows, out / "captures" / f"ingest_date={ingest_day.isoformat()}" / "captures.parquet", CAPTURE_SCHEMA)
        stats["rows"] += len(rows)
        stats["files"] += 1

    def emit(row: dict, lateness: int) -> None:
        row["ingested_at"] = row["captured_at"] + timedelta(days=lateness, minutes=rng.randint(5, 50))
        row["_ingest_date"] = row["ingested_at"].date()
        row["source_file"] = f"scraper/{row['_ingest_date'].isoformat()}/c{row['competitor_id']}.json"
        buffers[row["_ingest_date"]].append(row)

    for offset in range(days):
        capture_day = start + timedelta(days=offset)
        # cada concorrente é consultado numa rodada pela manhã; antecedência de 0 a 2 dias
        # é consultada de novo à tarde
        runs = {c[0]: [time(rng.randint(5, 8), rng.randint(0, 59)), time(rng.randint(13, 15), rng.randint(0, 59))] for c in COMPETITORS}

        for svc in services:
            for run_idx, run_time in enumerate(runs[svc.competitor_id]):
                ant_list = ANTECEDENCE_DAYS if run_idx == 0 else [0, 1, 2]
                for ant in ant_list:
                    dep_day = capture_day + timedelta(days=ant)
                    if ant == 0 and svc.departure_time <= run_time:
                        continue  # saída de hoje que já partiu
                    price, available = fare_and_seats(svc, dep_day, ant, level[svc.competitor_id], dynamic[svc.competitor_id])
                    sold_out = available == 0
                    stats["sold_out"] += sold_out
                    captured_local = datetime.combine(capture_day, run_time, LOCAL_TZ) + timedelta(seconds=rng.randint(0, 3000))
                    row = {
                        "competitor_id": svc.competitor_id,
                        "origin_name": spell(svc.competitor_id % 4, svc.origin_id),
                        "destination_name": spell(svc.competitor_id % 4, svc.destination_id),
                        "departure_at": datetime.combine(dep_day, svc.departure_time),
                        "service_class_label": svc.class_label,
                        "price": None if sold_out else price,
                        "seats_available": available,
                        "is_sold_out": sold_out,
                        "captured_at": captured_local.astimezone(timezone.utc),
                    }
                    lateness = 0 if rng.random() > 0.04 else rng.randint(1, 3)
                    stats["late"] += lateness > 0
                    emit(row, lateness)

                    if rng.random() < 0.02:  # reenvio, às vezes com preço corrigido
                        dup = {k: row[k] for k in row if k not in ("ingested_at", "_ingest_date", "source_file")}
                        if dup["price"] is not None and rng.random() < 0.4:
                            dup["price"] = round_fare(dup["price"] + rng.choice([-5, 5]))
                        emit(dup, lateness + rng.choice([0, 1]))
                        stats["duplicates"] += 1

        # ruído: rotas fora da nossa malha
        for _ in range(40):
            cid = rng.choice([c[0] for c in COMPETITORS if not c[3]])
            captured_local = datetime.combine(capture_day, time(rng.randint(5, 8), rng.randint(0, 59)), LOCAL_TZ)
            emit(
                {
                    "competitor_id": cid,
                    "origin_name": rng.choice(OUTSIDE),
                    "destination_name": spell(cid % 4, rng.randint(1, len(LOCALITIES))),
                    "departure_at": datetime.combine(capture_day + timedelta(days=rng.randint(1, 30)), time(rng.randint(6, 23), 0)),
                    "service_class_label": "Convencional",
                    "price": round_fare(rng.uniform(40, 200)),
                    "seats_available": rng.randint(1, 40),
                    "is_sold_out": False,
                    "captured_at": captured_local.astimezone(timezone.utc),
                },
                0,
            )
            stats["outside"] += 1

        for ingest_day in sorted(d for d in buffers if d < capture_day):
            flush(ingest_day)

    for ingest_day in sorted(buffers):
        flush(ingest_day)

    stats.update({"start": start.isoformat(), "end": end.isoformat(), "services": len(services)})
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("data"), help="pasta de saída")
    parser.add_argument("--days", type=int, default=180, help="quantidade de dias de captura")
    parser.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1), help="último dia de captura (AAAA-MM-DD)")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    s = generate(args.out, args.days, args.end, args.seed)
    print(
        f"{s['rows']:,} capturas em {s['files']} arquivos ({s['start']} a {s['end']}), {s['services']} serviços - "
        f"{s['sold_out']:,} esgotadas, {s['duplicates']:,} reenvios, {s['late']:,} atrasadas, {s['outside']:,} fora da malha"
    )
