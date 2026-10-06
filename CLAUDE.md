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
rustfs  ──────────────┐  (buckets: starrocks, warehouse, vcf, opendatalake-dev)
postgres ────────────┤  (DBs: airflow, radiant, polaris, keycloak — postgres-init-configmap.yaml)
   │                 │
   ├─> polaris/deploy (JDBC persistence in postgres, S3 in rustfs)
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
   ├─> worker (needs postgres + rustfs)
   ├─> ui   (needs api + keycloak)
   └─> airflow (PVs first, then helm; needs postgres, rustfs, polaris, starrocks)
          └─> Open Datalake Spark pods (optional; need the opendatalake-spark image
                                        + the polaris/starrocks opendatalake catalogs)
```

Seeding `data/` into RustFS (`aws s3 sync`) must happen **between** polaris deploy and polaris init — the init tables job reads `s3://warehouse/input_parquet/`.

## Wiring conventions

Everything talks over in-cluster service DNS on the `radiant` namespace. Credentials are hardcoded sandbox values, repeated across manifests — change one, grep for the rest.

| Service | DNS | Port(s) | Creds |
|---|---|---|---|
| RustFS | `radiant-rustfs` | 9000 api / 9001 console | `admin` / `password` |
| Postgres | `postgres` | 5432 | `postgres` / `postgres` |
| Polaris | `radiant-polaris` | 8181 catalog / 8182 mgmt | `root` / `password`, realm `radiant`, catalog `polaris` |
| StarRocks FE | `radiant-starrocks-fe` | 9030 mysql / 8030 http / 9020 thrift / 6090 starmgr | `root`, no password |
| StarRocks CN | `radiant-starrocks-cn` | 9050 heartbeat | — |
| Keycloak | `radiant-keycloak` | 8282 | admin `admin`/`admin`, realm `Radiant`, client `radiant` |
| API | `radiant-api` | 8090 | — |
| UI | `radiant-portal-ui` | 3000 | — |

Most services are `type: LoadBalancer`, so `minikube tunnel` exposes them on `localhost` at the same port. `radiant-keycloak` is the exception: its `KC_HOSTNAME` is `radiant-keycloak`, so `/etc/hosts` needs `127.0.0.1 radiant-keycloak` or OIDC redirects break.

**Every LoadBalancer gets EXTERNAL-IP `127.0.0.1`, so two services on the same port silently
fight over it.** `minikube tunnel` forks one `ssh -L <port>:<clusterIP>:<port>` per service and
never notices the collision — whichever wins the bind owns `localhost:<port>`, and it is not
necessarily the one you want. The usual way to end up with two is applying a component into the
wrong namespace (see the namespace reset below), then deploying it again into `radiant`: both
copies stay, both get forwarded.

The symptom is a connection that is *accepted and then reset*, never refused, because ssh is
listening fine and only the far end is dead:

```
$ aws s3 ls
Could not connect to the endpoint URL: "http://127.0.0.1:9000/"
```

`curl` reports the same as `(56) Recv failure: Connection reset by peer`. A plain refusal means
the tunnel is not running; a *reset* means it is running and pointed somewhere dead. Diagnose by
IP, not by port — line up the forwards against the live ClusterIPs:

```bash
ps aux | grep '[s]sh .*-L'                      # one line per forward, target ClusterIP visible
lsof -nP -iTCP:9000 -sTCP:LISTEN                # which pid actually won the bind
kubectl get svc -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,IP:.spec.clusterIP
```

Confirm the service itself is healthy from inside the cluster before blaming it — in-cluster
works while the host path is broken, which is the fingerprint:

```bash
kubectl run nettest --rm -i --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -sS -o /dev/null -w '%{http_code}\n' http://radiant-rustfs:9000/health/ready
```

Fix is to delete the duplicate service **and restart `minikube tunnel`** — it does not release a
forward whose backend disappeared.

One Polaris instance serves **two** catalogs, both in realm `radiant` under `root`/`password`:

| Catalog | Namespace | Warehouse | Written by | Read by |
|---|---|---|---|---|
| `polaris` | `radiant` | `s3://warehouse/polaris` | Radiant pipeline (PyIceberg) + the tables init job | StarRocks `radiant_iceberg_catalog` |
| `opendatalake` | `reference` | `s3://opendatalake-dev/iceberg` | Open Datalake Spark ETL | StarRocks `opendatalake_catalog` |

**StarRocks runs shared-data** (`run_mode = shared_data`, written into `fe.conf` by the FE deployment's start command), so internal tables live on `s3://starrocks` and the FE hosts the **starmgr** on port **6090**. The CN's starlet worker calls it for every `GetShard` and `WorkerHeartbeat`, so 6090 must stay published on `radiant-starrocks-fe-service.yaml` alongside 9030/9020/8030.

That dependency fails silently: starlet caches shard metadata in memory, so a cluster with 6090 missing keeps serving queries for as long as the CN stays up, and only breaks when the CN restarts with a cold cache. The symptom then looks like a storage fault, not a networking one:

```
SQL Error [1064]: starlet err grpc.GetShard(shardId=...) error: Deadline Exceeded: BE:10002
cn.WARNING: Report worker state to 'radiant-starrocks-fe:6090' error: ... Deadline Exceeded
```

Iceberg external catalogs (`radiant_iceberg_catalog`, `opendatalake_catalog`) are unaffected — they read RustFS directly and never touch starlet — so "external catalogs work, internal tables don't" is the fingerprint. Confirm with
`kubectl exec deploy/radiant-starrocks-cn -c radiant-starrocks-cn -- sh -c 'timeout 5 bash -c "</dev/tcp/radiant-starrocks-fe/6090"'`
and check the FE really listens (`ss -ltnp | grep 6090` in the FE pod) before suspecting RustFS.

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

# Seed RustFS (after polaris deploy, before polaris init). Plain S3 -- aws-cli, no vendor client.
export AWS_ACCESS_KEY_ID=admin AWS_SECRET_ACCESS_KEY=password AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL=http://127.0.0.1:9000
aws s3 sync data/input_parquet/ s3://warehouse/input_parquet/
aws s3 sync data/vcf/germline/ s3://vcf/
aws s3 sync data/vcf/somatic/ s3://vcf/

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

### After every `minikube start`

Three things reset and must be redone in this order — not just on first setup:

```bash
# 1. kubectl's namespace reverts to `default` (the context is recreated).
#    Do this BEFORE any `kubectl apply` -- nothing under k8s/ sets `metadata.namespace`, so an
#    apply made too early lands in `default` and is invisible to `kubectl get po` afterwards.
#    Re-applying into `radiant` does not remove that copy; it leaves a duplicate LoadBalancer
#    that hijacks the tunnel (see "Wiring conventions"). Recover with
#    `kubectl -n default delete -f k8s/<component>/` plus a tunnel restart.
kubectl config set-context --current --namespace=radiant

# 2. Both minikube mounts die with the VM; restart each in its own terminal
minikube mount $(pwd)/../radiant-portal-pipeline/radiant:/opt/airflow/dags/radiant
minikube mount $(pwd)/../radiant-open-datalake/airflow/opendatalake:/opt/airflow/dags/opendatalake

# 3. Kubelet already restarted the Airflow pods BEFORE those mounts existed, so they see empty
#    dirs. Restart them now (see the 9p propagation note below).
kubectl rollout restart deploy/airflow-dag-processor deploy/airflow-scheduler \
  statefulset/airflow-worker statefulset/airflow-triggerer
```

Step 3 is unavoidable with host mounts: kubelet always starts the pods before a mount can exist.
Only gitSync or baking DAGs into the image would remove it, and neither suits the live-edit loop.

## Validating changes

There is no cluster-free `kubectl` validation: `--dry-run=client` still contacts the API server for
resource resolution, so it fails with `connection refused` when Minikube is down. What does work:

```bash
# System python3 has no pyyaml; the sibling pipeline venv does.
PY=../radiant-portal-pipeline/.venv/bin/python

# Parse manifests and Helm values. NOTE the repo mixes extensions -- 32 .yaml and 5 .yml
# (k8s/api/, k8s/ui/, k8s/polaris/deploy/configs.yml), so a `*.yaml` glob silently skips five files.
$PY -c "import yaml,sys; [list(yaml.safe_load_all(open(f))) for f in sys.argv[1:]]" \
  $(git ls-files '*.yaml' '*.yml' | grep -v '^\.github')

# Helm extraEnv is a literal block scalar -- parse its INNER yaml separately, and the
# AIRFLOW_CONN_* entries as JSON, or a broken value only surfaces at pod start.
$PY -c "
import json,yaml
env=yaml.safe_load(yaml.safe_load(open('values/airflow3-values.yaml'))['extraEnv'])
names=[e['name'] for e in env]; assert len(names)==len(set(names)), 'duplicate env names'
[json.loads(next(e['value'] for e in env if e['name']==n)) for n in ('AIRFLOW_CONN_OPENDATALAKE_S3','AIRFLOW_CONN_RADIANT_API_CONN')]"

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
- **Locally-built images must exist before deploy.** `radiant-airflow3`, `radiant-airflow-task-operator`, `radiant-airflow-dbt-operator`, and `radiant-local-toolbox` are built into Minikube's docker daemon, never pulled. Tags in `values/airflow3-values.yaml` must match the tags used at build time. `ghcr.io/radiant-network/radiant-toolbox` is not pullable anonymously, so the toolbox is built from `../radiant-portal/backend/toolbox.Dockerfile` (context `../radiant-portal/backend`).
- **Airflow memory tuning is coupled.** `RADIANT_PARQUET_FILE_SIZE_MB` (64MB, down from the 500MB default) is what makes the SNV extraction pods fit in `RADIANT_TASK_OPERATOR_SNV_MEMORY_LIMIT: 1Gi`. Raise one and you must raise the other, or tasks OOMKill (exit 137). Sandbox-only — the 500MB default sits just under Iceberg's `WRITE_TARGET_FILE_SIZE_BYTES_DEFAULT` and lowering it in a real deployment produces many small parquet files.
- **Don't change install order** unless the dependency assumptions in the init jobs change with it (e.g. `polaris-init-tables` waits on the catalog job, which waits on Postgres + Polaris; RustFS must already hold the seed parquet).
- **Airflow 3 only.** `values/airflow2-values.yaml` was removed in `614fa5e`; the Airflow 2 path is gone.
- **Liveness probes need an `initialDelaySeconds` here.** The StarRocks probes ask the *FE* whether a node has registered, so they cannot pass until both FE and CN are up. Both originally started at t=0 — the CN allowed 3×10s = 30s, less than the 15s sleep in its own start command — so every `minikube start` killed them mid-boot with exit 137 and looped. Now 120s+5×10s (CN) and 90s+10×10s (FE). Keep a delay on any probe whose success depends on a *different* pod.
- **Resetting:** changing Docker's resource config requires deleting and recreating the Minikube VM — Docker/Minikube config drift is a known foot-gun.
- **The VM is oversubscribed.** StarRocks CN alone requests 4Gi (no limit) and the FE 1Gi, on top of 7 Airflow pods, Postgres, RustFS, Polaris, Keycloak and api/ui/worker. Adding a 2–3Gi Open Datalake Spark pod filled a 15.6GiB VM to 99% and thrashed it into unresponsiveness — `kubectl`, `minikube status` and even `docker exec … cat /proc/loadavg` all time out, and `minikube tunnel` reports TLS handshake timeouts. `docker stats --no-stream minikube` still works and is the fastest way to confirm it. Recovery is `minikube stop && minikube start` (PVs survive; only `minikube delete` destroys them). Don't run an Open Datalake import alongside a Radiant VCF import.
- **PRs** use `.github/pull_request_template.md`; branches and commits are named after JIRA issues (`feat/sjra-1888`, `feat: SJRA-1544 …`), and the template has `<!-- Begin/End JIRA Issues -->` markers that tooling fills in — leave them in place.

## Known state

- **Toolbox DAG wiring.** The pipeline's `Toolbox` K8s operator (`radiant/dags/operators/k8s.py`) reads its image from `RADIANT_TOOLBOX_OPERATOR_IMAGE` and its whole env via `envFrom` from secret `radiant-toolbox-secret` (`k8s/toolbox/`). An unset image is not a config error — the pod is submitted with no `image` and the API server rejects it with `422 … spec.containers[0].image: Required value`. The secret mirrors the API's `DB_*`/`PG*` env in `k8s/api/radiant-api-deployments.yml`; keep them in sync. There is no Ranger here, so `refresh-tenants` applies views and gene panel MVs and then fails at `refresh masking policies` — expected, like the Ranger steps of `create-tenant`/`create-user`.
- **A failed `helm install` skips the Airflow user.** `createUserJob` is a post-install hook, so an install that times out (e.g. `ImagePullBackOff` because a local image wasn't built yet) leaves the release `failed` and FAB with no users — every login is "invalid". `airflow users list` shows `No data found`. Fix with `helm upgrade` using the same values, which re-runs the hook and clears the `failed` status.
- The final step of `Radiant - Scheduled Import` is expected to fail. It triggers `Radiant - Data Integrity Checks`, which flags the deliberately imperfect sandbox data.
- **The object store is RustFS, and there is no vendor client.** It replaced MinIO, whose Docker Hub repositories (`docker.io/minio/minio`, `docker.io/minio/mc`) stopped serving anonymous pulls — *every* tag, `latest` included, 401s as ``pull access denied … repository does not exist or may require `docker login` ``, which reads like a typo'd tag but is not. `docker.io/rustfs/rustfs` has no such restriction. Everything here talks plain S3, so the bucket-init job and the seeding step both use `amazon/aws-cli` rather than a vendor CLI; don't reintroduce `mc`. RustFS config is env-driven (`RUSTFS_VOLUMES` is **required** — there is no positional `server /data` argument), it serves `/health` and `/health/ready` on the S3 port rather than MinIO's `/minio/health/live`, and it defaults to credentials `rustfsadmin`/`rustfsadmin`, which the deployment overrides to the sandbox's `admin`/`password`.
- `aws … | tail` makes `$?` the exit status of `tail`, so a failed copy still looks like success. Check the bucket rather than the pipeline's exit code: `aws s3 ls --recursive s3://<bucket>/ | wc -l`.
- `k8s/starrocks/radiant-starrocks-airflow-conn-secret.yaml` holds `AIRFLOW_CONN_STARROCKS_CONN` as JSON (parsed by `json.loads` in the dbt container), while `values/airflow3-values.yaml` sets the same variable as a MySQL URI for the scheduler. Both forms are intentional — don't unify them.
- **`RADIANT_OPEN_DATA_USE_LEGACY_TABLES` is inverted, and defaults to `*` (everything legacy).** It names the open-data sources to hold back on `radiant_iceberg_catalog.radiant.*`; anything *not* named is read from `opendatalake_catalog.reference.*`. So `*` is the most conservative value and the empty string is the most aggressive — blank means all 15 sources come from the OpenDataLake, which is the opposite of what a blank usually implies. Resolution lives in `radiant-portal-pipeline`'s `radiant/tasks/data/radiant_tables.py` (`get_open_data_legacy_keys` / `get_iceberg_open_data_mapping`); this repo only sets the value, in `values/airflow3-values.yaml`. Names accept the contract spelling or the legacy table name (`hpo_terms` = `hpo_term`), and an unknown name raises at parse time rather than silently staying legacy. `ensembl_gene`, `ensembl_exon_by_gene` and `cosmic_gene_set` have no OpenDataLake equivalent and are always legacy. Don't enable the variant-level sources (`dbsnp`, `dbnsfp`, `gnomad_joint`, `spliceai`, `topmed_bravo`, `1000_genomes`, `gnomad_sv`) in a sandbox — those are the full datasets, not the sampled seed. README's "Reading open data from the OpenDataLake" has the worked subset.
- Open Datalake table names are versioned and differ from Radiant's (`clinvar_v1` vs `clinvar`, `hpo_terms_v1` vs `hpo_term`, …), and each `dataset_version` is an Iceberg **branch** named after the version — `main` can be empty, so read a branch with `VERSION AS OF`. Per the design doc, 12 of the 20 tables Radiant consumes are covered; the rest still come from the seed parquet.
- Three Airflow pools must exist before the Open Datalake DAGs run, 1 slot each: `opendatalake_download_tasks_pool`, `opendatalake_direct_upload_tasks_pool`, `opendatalake_import_tasks_pool`.
- **`starrocks_insert_pool` needs `include_deferred=True`, not just 1 slot.** `Radiant - Re-annotate against OpenDataLake` (in `radiant-portal-pipeline`, `radiant/dags/reannotate_open_data.py`) runs every StarRocks statement through it. The operators `SUBMIT TASK` then defer, and `DEFERRED` is not in Airflow's `EXECUTION_STATES` — so `max_active_tis_per_dagrun` and the DAG's concurrency settings stop counting a statement the moment it starts doing work. A pool is the only limit that counts a deferred task, and only when created with `include_deferred=True`; created without it the pool releases the slot immediately and serialises nothing. Create it with `airflow pools set starrocks_insert_pool 1 "..." --include-deferred` (the UI checkbox is "Include deferred tasks", off by default). The DAG's `preflight_insert_pool` task asserts all three conditions before taking the import lock — that check exists because the misconfiguration is otherwise invisible until a BE dies on memory hours into a run that is holding the mutex. Full rationale in the pipeline repo's `radiant/dags/docs/reannotate_open_data.md`.
- `OPENDATALAKE_SPLICEAI_ACCESS_TOKEN` and `OPENDATALAKE_OMIM_DOWNLOAD_KEY` ship as **empty strings on purpose** — `SpliceAiConfig.missing()` / `OmimConfig.missing()` treat empty as unset and raise an `AirflowException` naming the variable, whereas a `<REPLACE_ME>` placeholder is sent to the remote as a real credential and returns an opaque auth error. Don't "fix" them back to placeholders.
- Shell inside the init ConfigMaps runs under `set -e` with `local`. `local x=$(cmd)` returns `local`'s status, not the command's, so `$?` is always 0 — write `local x; local status=0; x=$(cmd) || status=$?` instead. `radiant-polaris-init-catalog-script.yaml` had that bug; its "already bootstrapped" branch was unreachable until it was fixed.

## Open Data Lake integration

Testing SJRA-1811 (OpenDataLake tables feeding the Radiant ETL) means running both ETLs in **one**
sandbox. The choice made here is to reuse the Radiant stack rather than stand up the standalone
`opendatalake` namespace that `radiant-open-datalake/airflow/sandbox/` describes: same RustFS, same
Postgres, same Polaris, same StarRocks, same Airflow, all in the `radiant` namespace. Only the
delta lives in this repo.

What was added, and what it corresponds to upstream:

| Here | Upstream original | Difference |
|---|---|---|
| `opendatalake-dev` bucket in `k8s/rustfs/radiant-rustfs-bucket-init-job.yaml` | `k8s/minio/opendatalake-minio-bucket-init-job.yaml` | folded into the existing RustFS, no second instance |
| `k8s/polaris/init/radiant-polaris-init-opendatalake-catalog-job.yaml` | `k8s/polaris/polaris-catalog-init-job.yaml` | reuses the existing `radiant-polaris-init-catalog-script` ConfigMap with different env; JDBC-persisted realm `radiant` instead of a second in-memory Polaris on realm `POLARIS` |
| `k8s/starrocks/radiant-starrocks-opendatalake-catalog-job.yaml` | `sandbox/starrocks/create_iceberg_catalog.sql` | a Job against the existing FE, not a separate `allin1` StarRocks |
| `docker/opendatalake-spark/Dockerfile` | `airflow/sandbox/Dockerfile.opendatalake.spark` | unchanged except comments; build context is still the sibling repo's `spark/` |
| `opendatalake/operators/{k8s,spark_k8s}.py` | `airflow/sandbox/operators/` | namespace `radiant`, `radiant-rustfs`, `radiant-polaris`, credential `root:password`, scope `CATALOG_MANAGE_CONTENT`, explicit `Polaris-Realm` header, smaller pod resources |
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
  comment block that lists the other three: the RustFS init job, the Polaris catalog's
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
