# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Local sandbox for standing up the Radiant portal stack on Minikube. No application source here — only Kubernetes manifests (`k8s/`), Helm values (`values/`), an Airflow Dockerfile (`docker/`), and seed data (`data/`). Application code (API, worker, UI, DAGs) lives in sibling repos; this sandbox deploys their published images.

Two sibling repos must be cloned next to this one:
- `radiant-portal-pipeline` — Radiant DAGs (bind-mounted into Minikube) and the Dockerfiles for the task-operator and dbt-operator images.
- `radiant-open-datalake` — Open Datalake DAGs (also bind-mounted) and the Scala Spark ETL whose fat JAR goes into the `opendatalake-spark` image. Only needed for the Open Data Lake integration.

No tests, no lint, no build at repo level. Changes are validated by re-applying manifests and watching pod state.

## Dependency graph

Install order is fixed because each layer's init job assumes the previous is healthy:

```
minio  ──────────────┐  (buckets: starrocks, warehouse, vcf, opendatalake-dev)
postgres ────────────┤  (DBs: airflow, radiant, polaris, keycloak — postgres-init-configmap.yaml)
   │                 │
   ├─> polaris/deploy (JDBC persistence in postgres, S3 in minio)
   │      └─> polaris/init  (catalog job bootstraps realm+catalog+namespace;
   │                         tables job runs Spark to load data/input_parquet -> Iceberg;
   │                         opendatalake catalog job adds catalog `opendatalake` + ns `reference`)
   ├─> starrocks (FE shared-data on s3://starrocks; init job creates storage volume,
   │              radiant + radiant_tenant DBs, radiant_iceberg_catalog -> polaris,
   │              radiant_jdbc -> postgres/radiant; a second job adds
   │              opendatalake_catalog -> polaris catalog `opendatalake`)
   ├─> keycloak (realm `Radiant` imported from configmap)
   │
   ├─> api  (needs starrocks FE + postgres + keycloak)
   ├─> worker (needs postgres + minio)
   ├─> ui   (needs api + keycloak)
   └─> airflow (PVs first, then helm; needs postgres, minio, polaris, starrocks)
          └─> Open Datalake Spark pods (optional; need the opendatalake-spark image
                                        + the polaris/starrocks opendatalake catalogs)
```

`mc mirror` of `data/` into MinIO must happen **between** polaris deploy and polaris init — the init tables job reads `s3://warehouse/input_parquet/`.

## Wiring conventions

Everything talks over in-cluster service DNS on the `radiant` namespace. Credentials are hardcoded sandbox values, repeated across manifests — change one, grep for the rest.

| Service | DNS | Port(s) | Creds |
|---|---|---|---|
| MinIO | `radiant-minio` | 9000 api / 9001 console | `admin` / `password` |
| Postgres | `postgres` | 5432 | `postgres` / `postgres` |
| Polaris | `radiant-polaris` | 8181 catalog / 8182 mgmt | `root` / `password`, realm `radiant`, catalog `polaris` |
| StarRocks FE | `radiant-starrocks-fe` | 9030 mysql / 8030 http | `root`, no password |
| StarRocks CN | `radiant-starrocks-cn` | 9050 heartbeat | — |
| Keycloak | `radiant-keycloak` | 8282 | admin `admin`/`admin`, realm `Radiant`, client `radiant` |
| API | `radiant-api` | 8090 | — |
| UI | `radiant-portal-ui` | 3000 | — |

Most services are `type: LoadBalancer`, so `minikube tunnel` exposes them on `localhost` at the same port. `radiant-keycloak` is the exception: its `KC_HOSTNAME` is `radiant-keycloak`, so `/etc/hosts` needs `127.0.0.1 radiant-keycloak` or OIDC redirects break.

One Polaris instance serves **two** catalogs, both in realm `radiant` under `root`/`password`:

| Catalog | Namespace | Warehouse | Written by | Read by |
|---|---|---|---|---|
| `polaris` | `radiant` | `s3://warehouse/polaris` | Radiant pipeline (PyIceberg) + the tables init job | StarRocks `radiant_iceberg_catalog` |
| `opendatalake` | `reference` | `s3://opendatalake-dev/iceberg` | Open Datalake Spark ETL | StarRocks `opendatalake_catalog` |

For the `polaris` catalog, three separate clients each configure it their own way — keep them in sync: the Spark init job args (`k8s/polaris/init/radiant-polaris-init-tables-job.yaml`), the StarRocks external catalog (`k8s/starrocks/radiant-starrocks-init-job.yaml`), and the PyIceberg env vars in `values/airflow3-values.yaml`.

## Common operations

```bash
# Separate terminal, always first
minikube tunnel

# One-time namespace setup
kubectl create namespace radiant
kubectl config set-context --current --namespace=radiant

kubectl apply -f k8s/<component>/
kubectl get po | grep <component>

# Seed MinIO (after polaris deploy, before polaris init)
mc alias set localminio http://127.0.0.1:9000 admin password
mc mirror data/input_parquet/ localminio/warehouse/input_parquet/
mc mirror data/vcf/germline localminio/vcf/
mc mirror data/vcf/somatic localminio/vcf/

# Build images inside Minikube's docker so kubelet resolves them without a registry
eval $(minikube -p minikube docker-env)
docker build -t <tag> -f <Dockerfile> .

# Airflow: DAGs come from live host mounts, not a git-sync or baked image.
# One long-running `minikube mount` per package, each in its own terminal.
minikube mount $(pwd)/../radiant-portal-pipeline/radiant:/opt/airflow/dags/radiant
minikube mount $(pwd)/../radiant-open-datalake/airflow/opendatalake:/opt/airflow/dags/opendatalake

helm install airflow apache-airflow/airflow --version 1.21.0 -f values/airflow3-values.yaml

# Open Datalake Spark image: JAR first, then build with the SIBLING repo's spark/ as context
(cd ../radiant-open-datalake/spark && sbt clean assembly)
eval $(minikube -p minikube docker-env)
docker build -t ghcr.io/radiant-network/opendatalake-spark:latest \
  -f docker/opendatalake-spark/Dockerfile ../radiant-open-datalake/spark
```

## Validating changes

There is no cluster-free `kubectl` validation: `--dry-run=client` still contacts the API server for
resource resolution, so it fails with `connection refused` when Minikube is down. What does work:

```bash
# System python3 has no pyyaml; the sibling pipeline venv does.
PY=../radiant-portal-pipeline/.venv/bin/python

# Parse manifests and Helm values. NOTE the repo mixes extensions -- 29 .yaml and 5 .yml
# (k8s/api/, k8s/ui/, k8s/polaris/deploy/configs.yml), so a `*.yaml` glob silently skips five files.
$PY -c "import yaml,sys; [list(yaml.safe_load_all(open(f))) for f in sys.argv[1:]]" \
  $(git ls-files '*.yaml' '*.yml' | grep -v '^\.github')

# Helm extraEnv is a literal block scalar -- parse its INNER yaml separately, and the
# AIRFLOW_CONN_* entries as JSON, or a broken value only surfaces at pod start.
$PY -c "
import json,yaml
env=yaml.safe_load(yaml.safe_load(open('values/airflow3-values.yaml'))['extraEnv'])
names=[e['name'] for e in env]; assert len(names)==len(set(names)), 'duplicate env names'
json.loads(next(e['value'] for e in env if e['name']=='AIRFLOW_CONN_OPENDATALAKE_S3'))"

# Shell lives inside ConfigMaps and Job command blocks -- extract, then syntax-check
$PY -c "
import yaml; cm=yaml.safe_load(open('k8s/polaris/init/radiant-polaris-init-catalog-script.yaml'))
open('/tmp/polaris-init.sh','w').write(cm['data']['polaris-init.sh'])" && sh -n /tmp/polaris-init.sh

python3 -m py_compile opendatalake/operators/*.py
```

A wait-loop's failure path is worth actually running before trusting it — point it at an
unreachable host with a low attempt cap and confirm it exits non-zero instead of hanging.

## Editing guidance

- **Manifests are the contract.** Most work is YAML tweaks under `k8s/*/` or `values/`. Image tags and env vars (`RADIANT_TASK_OPERATOR_IMAGE`, `OPENDATALAKE_SPARK_IMAGE`) are the usual knobs.
- **Version pins live in two places.** The Airflow image tag is set in both `docker/airflow3/Dockerfile` (`apache/airflow:3.2.1-python3.12`, plus `requirements-airflow.txt` and the matching `constraints-python3.12.txt`) and `values/airflow3-values.yaml` (`defaultAirflowTag`, `airflowVersion`, `images.airflow.tag`). Bumping one alone silently deploys the wrong image. Same pattern for StarRocks `4.0.13` across the FE, CN, and init manifests.
- **Locally-built images must exist before deploy.** `radiant-airflow3`, `radiant-airflow-task-operator`, and `radiant-airflow-dbt-operator` are built into Minikube's docker daemon, never pulled. Tags in `values/airflow3-values.yaml` must match the tags used at build time.
- **Airflow memory tuning is coupled.** `RADIANT_PARQUET_FILE_SIZE_MB` (64MB, down from the 500MB default) is what makes the SNV extraction pods fit in `RADIANT_TASK_OPERATOR_SNV_MEMORY_LIMIT: 1Gi`. Raise one and you must raise the other, or tasks OOMKill (exit 137). Sandbox-only — the 500MB default sits just under Iceberg's `WRITE_TARGET_FILE_SIZE_BYTES_DEFAULT` and lowering it in a real deployment produces many small parquet files.
- **Don't change install order** unless the dependency assumptions in the init jobs change with it (e.g. `polaris-init-tables` waits on the catalog job, which waits on Postgres + Polaris; MinIO must already hold the seed parquet).
- **Airflow 3 only.** `values/airflow2-values.yaml` was removed in `614fa5e`; the Airflow 2 path is gone.
- **Resetting:** changing Docker's resource config requires deleting and recreating the Minikube VM — Docker/Minikube config drift is a known foot-gun.
- **PRs** use `.github/pull_request_template.md`; branches and commits are named after JIRA issues (`feat/sjra-1888`, `feat: SJRA-1544 …`), and the template has `<!-- Begin/End JIRA Issues -->` markers that tooling fills in — leave them in place.

## Known state

- The final step of `Radiant - Scheduled Import` is expected to fail. It triggers `Radiant - Data Integrity Checks`, which flags the deliberately imperfect sandbox data.
- `k8s/starrocks/radiant-starrocks-airflow-conn-secret.yaml` holds `AIRFLOW_CONN_STARROCKS_CONN` as JSON (parsed by `json.loads` in the dbt container), while `values/airflow3-values.yaml` sets the same variable as a MySQL URI for the scheduler. Both forms are intentional — don't unify them.
- The sandbox now *exposes* the Open Datalake tables as `opendatalake_catalog`, but `Radiant - Import Open Data` still reads `radiant_iceberg_catalog.radiant.*` (seeded from `data/input_parquet/`). Pointing it at the new catalog is the pipeline-side half of SJRA-1811, in `radiant-portal-pipeline` (`RADIANT_ICEBERG_CATALOG` / `ICEBERG_OPEN_DATA_MAPPING` in `radiant/tasks/data/radiant_tables.py`) — not a change to this repo.
- Open Datalake table names are versioned and differ from Radiant's (`clinvar_v1` vs `clinvar`, `hpo_terms_v1` vs `hpo_term`, …), and each `dataset_version` is an Iceberg **branch** named after the version — `main` can be empty, so read a branch with `VERSION AS OF`. Per the design doc, 12 of the 20 tables Radiant consumes are covered; the rest still come from the seed parquet.
- Three Airflow pools must exist before the Open Datalake DAGs run, 1 slot each: `opendatalake_download_tasks_pool`, `opendatalake_direct_upload_tasks_pool`, `opendatalake_import_tasks_pool`.
- `OPENDATALAKE_SPLICEAI_ACCESS_TOKEN` and `OPENDATALAKE_OMIM_DOWNLOAD_KEY` ship as **empty strings on purpose** — `SpliceAiConfig.missing()` / `OmimConfig.missing()` treat empty as unset and raise an `AirflowException` naming the variable, whereas a `<REPLACE_ME>` placeholder is sent to the remote as a real credential and returns an opaque auth error. Don't "fix" them back to placeholders.
- Shell inside the init ConfigMaps runs under `set -e` with `local`. `local x=$(cmd)` returns `local`'s status, not the command's, so `$?` is always 0 — write `local x; local status=0; x=$(cmd) || status=$?` instead. `radiant-polaris-init-catalog-script.yaml` had that bug; its "already bootstrapped" branch was unreachable until it was fixed.

## Open Data Lake integration

Testing SJRA-1811 (OpenDataLake tables feeding the Radiant ETL) means running both ETLs in **one**
sandbox. The choice made here is to reuse the Radiant stack rather than stand up the standalone
`opendatalake` namespace that `radiant-open-datalake/airflow/sandbox/` describes: same MinIO, same
Postgres, same Polaris, same StarRocks, same Airflow, all in the `radiant` namespace. Only the
delta lives in this repo.

What was added, and what it corresponds to upstream:

| Here | Upstream original | Difference |
|---|---|---|
| `opendatalake-dev` bucket in `k8s/minio/radiant-minio-bucket-init-job.yaml` | `k8s/minio/opendatalake-minio-bucket-init-job.yaml` | folded into the existing MinIO, no second instance |
| `k8s/polaris/init/radiant-polaris-init-opendatalake-catalog-job.yaml` | `k8s/polaris/polaris-catalog-init-job.yaml` | reuses the existing `radiant-polaris-init-catalog-script` ConfigMap with different env; JDBC-persisted realm `radiant` instead of a second in-memory Polaris on realm `POLARIS` |
| `k8s/starrocks/radiant-starrocks-opendatalake-catalog-job.yaml` | `sandbox/starrocks/create_iceberg_catalog.sql` | a Job against the existing FE, not a separate `allin1` StarRocks |
| `docker/opendatalake-spark/Dockerfile` | `airflow/sandbox/Dockerfile.opendatalake.spark` | unchanged except comments; build context is still the sibling repo's `spark/` |
| `opendatalake/operators/{k8s,spark_k8s}.py` | `airflow/sandbox/operators/` | namespace `radiant`, `radiant-minio`, `radiant-polaris`, credential `root:password`, scope `CATALOG_MANAGE_CONTENT`, explicit `Polaris-Realm` header, smaller pod resources |
| `OPENDATALAKE_*` block in `values/airflow3-values.yaml` | `airflow/sandbox/values/airflow-values.yaml` | merged into the Radiant values; the `AWS_*` vars are shared, not duplicated |

Things that bite:

- **The operators are templates, not live code.** They are copied into the sibling checkout
  (`opendatalake/lib/operators/`) and the DAG import path is rewritten with `sed`. The swap must
  never be committed to `radiant-open-datalake` — those operators have no place in the AWS
  deployment. `opendatalake/operators/*.py` won't import in *this* repo (no `opendatalake.lib`);
  that is expected.
- **Do not copy the sibling repo's own `sandbox/operators/`** — they hardcode the `opendatalake`
  namespace and `opendatalake-minio`/`polaris` service names, which don't exist here.
- **`Polaris-Realm` header.** The upstream operator omits it (its Polaris runs realm `POLARIS` as
  the sole realm). Here the header is set explicitly to `radiant`, matching what the Radiant Iceberg
  init job does.
- **Bucket name is load-bearing in four places**, each carrying an identical `SHARED CONSTANT`
  comment block that lists the other three: the MinIO init job, the Polaris catalog's
  `allowedLocations`, the `sed` rewrite in `docker/opendatalake-spark/Dockerfile` (which rewrites
  the JAR's baked `opendatalake-prd` config to `opendatalake-dev`), and `OPENDATALAKE_RAW_BUCKET` /
  `OPENDATALAKE_EMR_WAREHOUSE_S3` in `values/airflow3-values.yaml`. FerLab uses the Iceberg
  `StorageConf` path as the table LOCATION, so a mismatch shows up as a 404 `NoSuchBucket` on write,
  not as a config error. Keep the four comment blocks in sync when adding a fifth site.
- **`OPENDATALAKE_EMR_WAREHOUSE_S3` must include the `/reference` namespace segment**
  (`s3://opendatalake-dev/iceberg/reference`). Polaris derives a *per-namespace* location from
  `default-base-location` + namespace name and validates table locations against that, not against
  the catalog's broader `allowedLocations`:

  ```
  catalog   allowedLocations : s3://opendatalake-dev/iceberg
  namespace reference location: s3://opendatalake-dev/iceberg/reference/   <- what is enforced
  ```

  `--warehouse` replaces the ETL's storage root (`WapETLP.withStorageRoot`) and the table lands at
  `<warehouse>/<dataset path>`, e.g. `.../reference/normalized/clinvar_v1`. Drop the segment and
  writes go to `.../iceberg/normalized/<table>`, which Polaris rejects at commit time with
  `ForbiddenException: Invalid locations … is not in the list of allowed locations`. Only the
  scheme differs from `opendatalake/lib/config.py`'s default — `s3://`, not `s3a://`, because the
  allowed locations are `s3://` and the prefix check is textual. Inspect the real values rather
  than reasoning from the config code:
  `curl -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: radiant" http://localhost:8181/api/catalog/v1/opendatalake/namespaces/reference`
- **Memory.** The Spark pod defaults are deliberately lower than upstream (2Gi request / 3Gi limit /
  2g driver vs 4Gi/6Gi/4g) because it now competes with StarRocks CN, the FE and the Airflow pods in
  the same 12GB Minikube. Raise `OPENDATALAKE_SPARK_MEMORY*` and `OPENDATALAKE_SPARK_DRIVER_MEMORY`
  together if an import OOMKills (exit 137).
- **No Airflow image change was needed.** The Open Datalake DAGs import `airflow.providers.amazon`
  at parse time, but `apache/airflow:3.2.1-python3.12` already bundles it at 9.25.0 — the exact
  version `constraints-python3.12.txt` pins (29 providers ship in that image). Verify after a
  base-image bump rather than assuming, with
  `docker run --rm --user airflow --entrypoint python apache/airflow:3.2.1-python3.12 -c "import importlib.metadata as m; print(m.version('apache-airflow-providers-amazon'))"`.
  Note the image's entrypoint is `airflow`, so `docker run … pip show …` silently runs
  `airflow pip show` instead — use `--entrypoint`.
- **Two DAG mounts now.** `radiant-portal-pipeline/radiant` and
  `radiant-open-datalake/airflow/opendatalake`, both under `/opt/airflow/dags/`, each its own
  long-running `minikube mount`.
- **Mount before Airflow starts — 9p submounts don't propagate into running pods.** The pods
  bind-mount `/opt/airflow/dags` at startup; a `minikube mount` created *after* that stays invisible
  to them, and the pod keeps showing the empty directory underneath. Diagnostic signature: DAGs
  missing from the UI with **zero import errors** (the processor's file table simply has no
  `opendatalake/` rows), `minikube ssh -- ls /opt/airflow/dags/opendatalake` full, and
  `kubectl exec deploy/airflow-dag-processor -c dag-processor -- ls /opt/airflow/dags/opendatalake`
  empty and `root:root` (a live mount shows `1000:999`). Fix is `kubectl rollout restart` on
  dag-processor, scheduler, worker and triggerer — not a re-mount.
- **`run_sql_on_iceberg.py` cannot be swapped** and will always show one import error asking for
  `OPENDATALAKE_EMR_*`. It runs in PySpark mode (`entry_point=` with an uploaded script) while
  `spark_k8s.py` implements only JAR mode, so a blind `sed` across all DAGs trades the EMR-config
  error for a `TypeError: unexpected keyword argument 'entry_point'`. The swap must stay scoped to
  `import_source.py` (and `download_source.py` for the ECS→K8s one).
