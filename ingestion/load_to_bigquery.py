"""Carrega os arquivos Parquet gerados no dataset `raw` do BigQuery.

Decisões:
- Carga em lote (load job), não streaming: load jobs são gratuitos e
  funcionam também no sandbox do BigQuery.
- `raw.price_captures` é particionada por DATA DE INGESTÃO (_ingest_date)
  e clusterizada por competitor_id e origin_name.
- Cada arquivo é carregado na sua própria partição com WRITE_TRUNCATE
  (tabela$AAAAMMDD). Rodar a carga de novo para o mesmo dia substitui a
  partição em vez de duplicar: a carga é idempotente.
- A tabela exige filtro de partição (require_partition_filter), para que
  nenhuma consulta leia o histórico inteiro sem querer.

Uso:
    # carga a partir dos arquivos locais
    python load_to_bigquery.py --project MEU_PROJETO --data ../data

    # só um intervalo de datas de ingestão (simula a carga diária)
    python load_to_bigquery.py --project MEU_PROJETO --data ../data --start 2026-11-01 --end 2026-11-03

    # passando pelo Cloud Storage
    python load_to_bigquery.py --project MEU_PROJETO --data ../data --bucket meu-bucket

Autenticação: `gcloud auth application-default login` ou a variável
GOOGLE_APPLICATION_CREDENTIALS apontando para a chave de uma service account.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from google.cloud import bigquery, storage

CAPTURES_SCHEMA = [
    bigquery.SchemaField("competitor_id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("origin_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("destination_name", "STRING", mode="REQUIRED"),
    # horário local da saída: DATETIME (sem fuso), como aparece no site
    bigquery.SchemaField("departure_at", "DATETIME", mode="REQUIRED"),
    bigquery.SchemaField("service_class_label", "STRING"),
    bigquery.SchemaField("price", "FLOAT64", description="nulo quando a saída está esgotada"),
    bigquery.SchemaField("seats_available", "INT64"),
    bigquery.SchemaField("is_sold_out", "BOOL"),
    # momento da captura: TIMESTAMP (UTC)
    bigquery.SchemaField("captured_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("_ingest_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("source_file", "STRING"),
]

DIMENSIONS = ["competitors", "localities", "routes", "locality_aliases"]


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)


def ensure_captures_table(client: bigquery.Client, table_id: str) -> None:
    table = bigquery.Table(table_id, schema=CAPTURES_SCHEMA)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="_ingest_date"
    )
    table.clustering_fields = ["competitor_id", "origin_name"]
    table.require_partition_filter = True
    table.description = "Capturas brutas de tarifas de concorrentes, uma partição por data de ingestão."
    client.create_table(table, exists_ok=True)


def upload_to_gcs(bucket_name: str, local: Path, blob_name: str) -> str:
    bucket = storage.Client().bucket(bucket_name)
    bucket.blob(blob_name).upload_from_filename(str(local))
    return f"gs://{bucket_name}/{blob_name}"


def load_file(
    client: bigquery.Client,
    local: Path,
    destination: str,
    job_config: bigquery.LoadJobConfig,
    bucket: str | None,
    blob_name: str,
) -> int:
    if bucket:
        uri = upload_to_gcs(bucket, local, blob_name)
        job = client.load_table_from_uri(uri, destination, job_config=job_config)
    else:
        with local.open("rb") as fh:
            job = client.load_table_from_file(fh, destination, job_config=job_config)
    job.result()  # espera terminar e levanta exceção se falhar
    return job.output_rows or 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--dataset", default="raw")
    parser.add_argument("--location", default="US")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bucket", help="se informado, envia os arquivos ao GCS antes de carregar")
    parser.add_argument("--start", type=date.fromisoformat, help="primeira data de ingestão a carregar")
    parser.add_argument("--end", type=date.fromisoformat, help="última data de ingestão a carregar")
    parser.add_argument("--skip-dimensions", action="store_true")
    args = parser.parse_args()

    client = bigquery.Client(project=args.project, location=args.location)
    dataset_id = f"{args.project}.{args.dataset}"
    ensure_dataset(client, dataset_id, args.location)

    if not args.skip_dimensions:
        for name in DIMENSIONS:
            config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.PARQUET,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            )
            rows = load_file(
                client,
                args.data / "dimensions" / f"{name}.parquet",
                f"{dataset_id}.{name}",
                config,
                args.bucket,
                f"dimensions/{name}.parquet",
            )
            print(f"{name}: {rows:,} linhas")

    table_id = f"{dataset_id}.price_captures"
    ensure_captures_table(client, table_id)

    folders = sorted((args.data / "captures").glob("ingest_date=*"))
    total = 0
    for folder in folders:
        ingest_day = date.fromisoformat(folder.name.split("=", 1)[1])
        if (args.start and ingest_day < args.start) or (args.end and ingest_day > args.end):
            continue
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=CAPTURES_SCHEMA,
        )
        partition = f"{table_id}${ingest_day.strftime('%Y%m%d')}"
        rows = load_file(
            client,
            folder / "captures.parquet",
            partition,
            config,
            args.bucket,
            f"captures/{folder.name}/captures.parquet",
        )
        total += rows
        print(f"{ingest_day}: {rows:,} linhas")

    print(f"Total de capturas carregadas: {total:,}")


if __name__ == "__main__":
    main()
