# Radiant Portal Sandbox

This project is a sandbox for installing Radiant portal stack components locally. 

It is ONLY intended to be used for testing and development purposes, allowing users to experiment with the Radiant portal stack.

# Requirements
Software requirements to run this project locally:
- Docker
- Minikube 
- Kubectl
- Helm

Hardware requirements to run this project locally:
- 16 GB RAM
- 30 GB Disk Space
- 4 CPU Cores

Configure Docker to use at least 16 GB of RAM and 4 CPU Cores.

Note: if you change docker configuration, you need to delete your minikube.

Configure minikube to use at least 16 GB of RAM and 4 CPU Cores:
(You'll need at least 24 GB if you deploy the OpenDataLake setup as well)

```
minikube config set memory 16000
minikube config set cpus 4
```

# Installation


## Run minikube tunnel in a separate terminal
```
minikube tunnel
```

## Create a namespace for the project
```
kubectl create namespace radiant
```

## Switch to the radiant namespace
```
kubectl config set-context --current --namespace=radiant
```

## Install RustFS
```
kubectl apply -f k8s/rustfs/
```

## Monitor RustFS pods are running (1 minutes)
```
kubectl get po | grep rustfs
```
Results 1 pod running and 1 pod completed:
```
radiant-rustfs-bucket-init-job-2znb9   0/1     Completed   0          103s
radiant-rustfs-d7cf486cf-22zlg         1/1     Running     0          103s
```

## Install postgres
```
kubectl apply -f k8s/postgres/
```

## Monitor Postgres pods are running (1 minutes)
```
kubectl get po | grep postgres
```
Results 1 pod running and 1 pod completed:
```
postgres-585445b9cc-gxnvx             1/1     Running     0          23s
postgres-init-job-fhtgf               0/1     Completed   0          23s
```

## Install polaris
```
kubectl apply -f k8s/polaris/deploy
```

## Monitor polaris pod is running (1 minute)
```
kubectl get po | grep radiant-polaris
```
Results 1 pod running:
```
radiant-polaris-6c6c96bc58-ncpbv      1/1     Running     0          38s
```

## Seed the buckets with the sample data

RustFS speaks S3, so the AWS CLI is all you need — there is no RustFS-specific client to install.

On Mac :
```
brew install awscli
```

Point it at the tunnelled RustFS and copy `data/` in. These are the sandbox credentials from
`k8s/rustfs/radiant-rustfs-deployment.yaml`; exporting them for the shell avoids repeating
`--endpoint-url` flags with a profile you do not want to keep:
```
export AWS_ACCESS_KEY_ID=admin
export AWS_SECRET_ACCESS_KEY=password
export AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL=http://127.0.0.1:9000

aws s3 sync data/input_parquet/ s3://warehouse/input_parquet/
aws s3 sync data/vcf/germline/ s3://vcf/
aws s3 sync data/vcf/somatic/ s3://vcf/
```

Verify — expect 35 objects under `warehouse/input_parquet/` and 20 under `vcf/`:
```
aws s3 ls --recursive s3://warehouse/input_parquet/ | wc -l
aws s3 ls --recursive s3://vcf/ | wc -l
```

`AWS_ENDPOINT_URL` is honoured by AWS CLI v2.22 and later. On an older CLI, pass
`--endpoint-url http://127.0.0.1:9000` on each command instead.

## Init Polaris Catalog and tables
```
kubectl apply -f k8s/polaris/init
```

## Monitor Init Polaris Catalog and Tables (2 minutes)

```
kubectl get po | grep polaris-init
```

Results 2 pods running:
```
radiant-polaris-init-catalog-zdk4r      0/1     Completed   0          93s
radiant-polaris-init-tables-job-4kw5f   0/1     Completed   0          93s
```

## Install Starrocks
```
kubectl apply -f k8s/starrocks/
```

## Monitor Starrocks pods are running (5 minutes the first time, due to large image pulling)
```
kubectl get po | grep starrocks
```
Results 2 pods running and 1 pod completed:
```
radiant-starrocks-cn-549678f95d-klrzc    1/1     Running     0          3m51s
radiant-starrocks-fe-5fd6df97fd-5dj55    1/1     Running     0          3m51s
radiant-starrocks-init-job-wszgc         0/1     Completed   0          3m51s
```

## Install keycloak
```
kubectl apply -f k8s/keycloak/
```

## Monitor Keycloak pod is running (1 minutes)
```
kubectl get po | grep keycloak
```
Results 1 pod running :
```
radiant-keycloak-b544d74bb-wk5zv         1/1     Running     0          53s
```

## Install API
```
kubectl apply -f k8s/api/
```

## Monitor API pod is running (1 minutes)
```
kubectl get po | grep api
```
Results 1 pod running :
```
radiant-api-6d58b89d8b-gkf8r             0/1     Running     0          25s
```

## Verify the status of the API :
```
curl http://localhost:8090/status
{"status":{"postgres":"up","starrocks":"up"}}%
```

## Install Worker
```
kubectl apply -f k8s/worker/
```

## Monitor API pod is running (1 minutes)
```
kubectl get po | grep worker
```
Results 1 pod running :
```
radiant-worker-5c9bd9c9c5-775m5          1/1     Running     0          108s
```

## Install the frontend
```
kubectl apply -f k8s/ui/
```

## Monitor Frontend pod is running (1 minutes)
```
kubectl get po | grep ui
```
Results 1 pod running :
```
radiant-portal-ui-7659677b49-g5mjx       1/1     Running     0          25s
```

## Mount volume for dags in minikube

Checkout the radiant-portal-pipeline project repository to your local workspace :
```
cd YOUR_WORKSPACE
git clone git@github.com:radiant-network/radiant-portal-pipeline.git
```

Then in a new terminal, run the following command to mount the dags directory in minikube:
```
minikube mount $(pwd)/radiant-portal-pipeline/radiant:/opt/airflow/dags/radiant
```
Let this command run in a separate terminal while you are working with Airflow.

> **Testing the Open Data Lake integration?** Start its DAG mount now too, in its own terminal —
> see [Open Data Lake integration](#open-data-lake-integration). Both mounts must exist *before*
> Airflow is installed below; a mount created afterwards does not propagate into the running pods.

## Pre-building the Radiant task operator image (~6 minutes)

Inside the `radiant-portal-pipeline` directory, run the following command to build the Radiant task operator image:

```
eval $(minikube -p minikube docker-env)  # To ensure the image is built inside minikube's docker environment
docker build -t ghcr.io/radiant-network/radiant-airflow-task-operator:latest -f Dockerfile.radiant.operator .
```

## Pre-building the Radiant dbt operator image

Inside the `radiant-portal-pipeline` directory, run the following command to build the Radiant task operator image:

```
eval $(minikube -p minikube docker-env)  # To ensure the image is built inside minikube's docker environment
docker build -t ghcr.io/radiant-network/radiant-airflow-dbt-operator:latest -f Dockerfile.radiant.dbt .
```

**Important note:** Ensure the image's name and tag matches with the `RADIANT_TASK_OPERATOR_IMAGE` from the `values/airflow3-values.yaml` file.

> **Testing the Open Data Lake integration?** Build its two images now as well, and apply the
> operator swaps — both before the Airflow install below. See
> [Open Data Lake integration](#open-data-lake-integration).

## Install airflow volumes for logs and dags
```
kubectl apply -f k8s/airflow/
```

## Install Airflow

- Build the docker image:
  ```
  cd docker/airflow3
  eval $(minikube -p minikube docker-env)
  docker build -t ghcr.io/radiant-network/radiant-airflow3:1.0.10 .
  ```
- Install via helm:
  ```
	helm install airflow apache-airflow/airflow  --version 1.21.0  -f values/airflow3-values.yaml
  ```

Took 5 minutes to install Airflow

## Monitor Airflow pod are running (5 minutes)
```
kubectl get po | grep airflow
```
Results 4 pods running:
```
airflow-scheduler-6644cb8c5d-rcncc       2/2     Running     0          99s
airflow-statsd-75fdf4bc64-7w9sb          1/1     Running     0          99s
airflow-triggerer-0                      2/2     Running     0          99s
airflow-webserver-744898d99-nvxrn        1/1     Running     0          99s
```

## Configure airflow
Connect to the Airflow UI at http://localhost:8080
- Username: airflow
- Password: airflow

Then Unpause all the dags by sliding the toggle button of each dag to the right.

Configure the pools :
- Go to Admin -> Pools
- Create a new pool named "import_part" with 1 slot
- Create a new pool named "import_vcf" with 128 slots
- Create a new pool named "starrocks_insert_pool" with 1 slot **and "Include deferred tasks"
  ticked** — see below

Only if you are testing the Open Data Lake integration, create these three as well, 1 slot each
(plain pools — they do *not* need "Include deferred tasks"):
- `opendatalake_download_tasks_pool`
- `opendatalake_direct_upload_tasks_pool`
- `opendatalake_import_tasks_pool`

`starrocks_insert_pool` serialises the StarRocks statements in `Radiant - Re-annotate against
OpenDataLake`. All three of its settings matter, and the **"Include deferred tasks"** checkbox is
the one that is easy to miss — it is off by default and the pool silently serialises nothing
without it. The Radiant StarRocks operators `SUBMIT TASK` and then defer, and Airflow's scheduler
counts only `EXECUTION_STATES` (`RUNNING`, `QUEUED`); a task stops being counted the moment its
statement actually starts, so `max_active_tis_per_dagrun` and the DAG's concurrency settings do not
constrain it. A pool is the only Airflow limit that counts a `DEFERRED` task, and only when created
with `include_deferred=True`.

From the CLI instead of the UI:
```
kubectl exec deploy/airflow-scheduler -c scheduler -- \
  airflow pools set import_part 1 "Serialise import_part"
kubectl exec deploy/airflow-scheduler -c scheduler -- \
  airflow pools set import_vcf 128 "VCF import fan-out"
kubectl exec deploy/airflow-scheduler -c scheduler -- \
  airflow pools set starrocks_insert_pool 1 "Serialise StarRocks inserts" --include-deferred

# Open Data Lake only
kubectl exec deploy/airflow-scheduler -c scheduler -- \
  airflow pools set opendatalake_download_tasks_pool 1 "Open Datalake download tasks"
kubectl exec deploy/airflow-scheduler -c scheduler -- \
  airflow pools set opendatalake_direct_upload_tasks_pool 1 "Open Datalake direct upload tasks"
kubectl exec deploy/airflow-scheduler -c scheduler -- \
  airflow pools set opendatalake_import_tasks_pool 1 "Open Datalake import tasks"
```
Verify with `kubectl exec deploy/airflow-scheduler -c scheduler -- airflow pools list`.

## Run dags
Trigger the following dags in order. Each dag takes a few minutes to run. Wait for each dag to complete before triggering the next one.
1. Trigger dag `[QA] Radiant - Init Simulated Clinical Data`
   - Set vcf_bucket_prefix to `s3://vcf`
2. Trigger dag `Radiant - Init StarRocks Base Tables` (~ 2 minutes)
3. Trigger dag  `Radiant - Init Iceberg Tables` (~ 1 minutes)
4. Trigger dag `Radiant - Import Open Data` (~ 5 minutes)
   - Leave `skip_legacy_tables` unchecked.
   - In raw_rcv_filepaths, set the value `s3://warehouse/input_parquet/clinvar_rcv_summary/*.json`
   - In cytoband_filepath, set the value `s3://warehouse/input_parquet/cytoband/*.txt.gz`
5. Trigger dag `Radiant - Scheduled Import` (~ 5 minutes)

The last step of Radiant - Scheduled Import will fail — this is expected: it triggers Radiant - Data Integrity Checks, which flags the (deliberately imperfect) sandbox test data.

## Edit /etc/host file 
Add the following line to your /etc/hosts file to access the keycloak admin console:
```
127.0.0.1  radiant-keycloak
```

## Create user in keycloak 
Log into keycloak admin console for creating a user
http://radiant-keycloak:8282/
Username: `admin`
Password: `admin`

Click on `Manage Realms`, then click on `Radiant`.

Click on `Users`, then click on `Create a new User`.

- Email verified: `ON`
- Username: `user1` (or any username you want)
- Email: `user1@email.me` (or any email you want)
- First Name: `User1` (or any first name you want)
- Last Name: `Test` (or any last name you want)
- Confirm by clicking on `Create` button.

Click on `Credentials` tab, then click on `Set Password`.

- Password: `user1` (or any password you want)
- Password confirmation: `user1` (or any password you want)
- Temporary: `OFF`
- Confirm by clicking on `Save Password`

Click on `Role Mappings` tab

Click on `Assign Roles`, then select `Client Roles`.

Select `radiant` in the table and then click on `Assign` Button.

## Connect to Radiant Portal UI
Open a new browser tab and go to http://localhost:3000

You should be redirected to keycloak login page. Put the username and password you just created.
Then you should be able to see the case list page.

If you click on Case 1 (Family trio) or case 8 (Solo), you should be able to click on Variants tab and see the variants for the case.

## Open Data Lake integration

(Ignore this section if you are not testing the OpenDataLake → Radiant ETL integration)

The unified sandbox runs the [radiant-open-datalake](https://github.com/radiant-network/radiant-open-datalake)
ETL **inside this stack** rather than as a separate minikube: it reuses the RustFS, Postgres, Polaris,
StarRocks and Airflow installed above, all in the `radiant` namespace. The Open Datalake ETL writes
Iceberg tables into their own Polaris catalog (`opendatalake`, namespace `reference`), and StarRocks
attaches them as the external catalog `opendatalake_catalog`, so Radiant's open-data DAG can read
them.

```
radiant-open-datalake DAGs (in the same Airflow)
   └─> Spark pod (spark-submit --master local[*])
         ├── raw in:  s3://opendatalake-dev/raw/landing/<source>/<version>   (RustFS)
         └── out:     Polaris catalog `opendatalake` -> s3://opendatalake-dev/iceberg/reference
                          └─> StarRocks external catalog `opendatalake_catalog`
                                └─> Radiant - Import Open Data
```

### Where this fits in the install

Starting from scratch, the **infrastructure needs no extra manifests**. The bucket, the Polaris
catalog and the StarRocks catalog all ship inside directories that the base install already applied:

| Created by | Manifest (already applied above) |
|---|---|
| `opendatalake-dev` bucket | `k8s/rustfs/radiant-rustfs-bucket-init-job.yaml` |
| Polaris catalog `opendatalake` + namespace `reference` (warehouse `s3://opendatalake-dev/iceberg`) | `k8s/polaris/init/radiant-polaris-init-opendatalake-catalog-job.yaml` |
| StarRocks external catalog `opendatalake_catalog` | `k8s/starrocks/radiant-starrocks-opendatalake-catalog-job.yaml` |

The Open Datalake env vars are likewise already in `values/airflow3-values.yaml`.

What you *do* add are five steps, and three of them have to land at a specific point in the flow
above — not here at the end:

| Run it at | Step |
|---|---|
| Before you start | [1. Clone the sibling repository](#1-clone-the-sibling-repository) |
| *Pre-building the Radiant task operator image* | [2. Build the Open Datalake images](#2-build-the-open-datalake-images) |
| *Pre-building the Radiant task operator image* | [3. Apply the sandbox operator swaps](#3-apply-the-sandbox-operator-swaps) |
| *Mount volume for dags in minikube* | [4. Mount the Open Datalake DAGs](#4-mount-the-open-datalake-dags) |
| *Configure airflow* | [5. Create the pools and fill in credentials](#5-create-the-pools-and-fill-in-credentials) |

Steps 3 and 4 must both be done **before `helm install airflow`**. The DAG mount does not propagate
into pods that are already running, and the operator swap changes what the DAG files import — doing
either afterwards means a `kubectl rollout restart` (see [Troubleshooting](#troubleshooting)).

> **Already have a sandbox running?** The three manifests above are the only infrastructure delta.
> Re-run the finished jobs to pick them up, then continue at step 1:
> ```
> kubectl delete job radiant-rustfs-bucket-init-job
> kubectl apply -f k8s/rustfs/
> kubectl apply -f k8s/polaris/init/
> kubectl apply -f k8s/starrocks/
> helm upgrade airflow apache-airflow/airflow --version 1.21.0 -f values/airflow3-values.yaml
> ```

### 1. Clone the sibling repository

Check out `radiant-open-datalake` next to this repo, the same way as `radiant-portal-pipeline`:
```
cd YOUR_WORKSPACE
git clone git@github.com:radiant-network/radiant-open-datalake.git
```

Once the base install has reached *Install Starrocks*, confirm the three pieces exist:
```
kubectl get po | grep -E "opendatalake|bucket-init"
aws s3 ls s3://opendatalake-dev/
kubectl exec -it deploy/radiant-starrocks-fe -- mysql -P9030 -h127.0.0.1 -uroot -e "SHOW CATALOGS;"
```
Expect `radiant-rustfs-bucket-init-job-*`, `radiant-polaris-init-opendatalake-catalog-*` and
`radiant-starrocks-opendatalake-catalog-job-*` all `Completed`, and `SHOW CATALOGS` listing
`radiant_iceberg_catalog`, `radiant_jdbc` and `opendatalake_catalog`.

### 2. Build the Open Datalake images

Two images, both built into minikube's docker daemon so kubelet resolves them without a registry.

The Spark ETL image bundles the Scala fat JAR. Build the JAR first, then the image — the build
context is the sibling repo's `spark/` directory, and the Dockerfile lives here:
```
cd ../radiant-open-datalake/spark
sbt clean assembly

cd ../../radiant-portal-sandbox
eval $(minikube -p minikube docker-env)
docker build -t ghcr.io/radiant-network/opendatalake-spark:latest \
  -f docker/opendatalake-spark/Dockerfile ../radiant-open-datalake/spark
```

The download task-operator image is built from the sibling repo (its Dockerfile needs that repo's
`requirements*.txt` as context):
```
cd ../radiant-open-datalake/airflow
eval $(minikube -p minikube docker-env)
docker build -t ghcr.io/radiant-network/opendatalake-airflow-task-operator:latest \
  -f Dockerfile.opendatalake.operator .
```

Both tags must match `OPENDATALAKE_SPARK_IMAGE` and `OPENDATALAKE_TASK_OPERATOR_IMAGE` in
`values/airflow3-values.yaml`.

No Airflow image rebuild is needed: the Open Datalake DAGs import `airflow.providers.amazon`, which
the base image already bundles at the version `docker/airflow3/constraints-python3.12.txt` pins.

### 3. Apply the sandbox operator swaps

The Open Datalake DAGs target AWS (ECS for downloads, EMR Serverless for Spark). Swap both for the
in-cluster Kubernetes equivalents. The versions in `opendatalake/operators/` are this sandbox's
variants — they use the `radiant` namespace, `radiant-rustfs` and `radiant-polaris`, unlike the ones
in the sibling repo's own `sandbox/operators/`, which assume a standalone `opendatalake` namespace.

```
cp opendatalake/operators/k8s.py \
   ../radiant-open-datalake/airflow/opendatalake/lib/operators/k8s.py
cp opendatalake/operators/spark_k8s.py \
   ../radiant-open-datalake/airflow/opendatalake/lib/operators/spark_k8s.py

cd ../radiant-open-datalake/airflow
sed -i '' 's/operators\.ecs/operators\.k8s/g' opendatalake/dags/download_source.py
sed -i '' 's/operators\.emr/operators\.spark_k8s/g' opendatalake/dags/import_source.py
```

To revert:
```
cd ../radiant-open-datalake/airflow
sed -i '' 's/operators\.k8s/operators\.ecs/g' opendatalake/dags/download_source.py
sed -i '' 's/operators\.spark_k8s/operators\.emr/g' opendatalake/dags/import_source.py
rm opendatalake/lib/operators/k8s.py opendatalake/lib/operators/spark_k8s.py
```

**Do not commit the swap** to `radiant-open-datalake` — those operators have no place in the AWS
deployment.

`opendatalake/dags/run_sql_on_iceberg.py` is deliberately **not** swapped and will show a DAG import
error in the UI ("Incomplete EMR Serverless configuration; missing field(s): application_id, …").
It is a debugging utility, not part of the integration path, and it cannot use the sandbox operator
as-is: it runs in PySpark mode (passes `entry_point=` with an uploaded `.py` script), whereas
`spark_k8s.py` only implements JAR mode (`--class <entry_class> <jar>`). One import error is the
expected steady state; the other 33 opendatalake DAGs are unaffected. To silence the banner, either
set the six `OPENDATALAKE_EMR_*` variables it names to dummy values in `values/airflow3-values.yaml`
(the DAG then parses but still cannot run without EMR), or leave it as-is.

### 4. Mount the Open Datalake DAGs

In a new terminal, alongside the `radiant` mount already running:
```
minikube mount $(pwd)/radiant-open-datalake/airflow/opendatalake:/opt/airflow/dags/opendatalake
```
The package is mounted *under* the DAGs folder (not as the DAGs folder) so the DAG files'
`from opendatalake... import` statements resolve — `/opt/airflow/dags` is on `PYTHONPATH` and must
contain the `opendatalake/` package root. Leave this running like the `radiant` mount.

Both mounts die with the VM on every `minikube stop`, and must be restarted — followed by a
`kubectl rollout restart` of the Airflow components, because kubelet restarts those pods before the
mounts can exist. See [Troubleshooting](#troubleshooting).

### 5. Create the pools and fill in credentials

The three `opendatalake_*_tasks_pool` pools are created at the [Configure airflow](#configure-airflow)
step, alongside the Radiant ones — nothing extra to do here if you followed it.

Note that `starrocks_insert_pool`, listed there too, belongs to the Radiant side (`Radiant -
Re-annotate against OpenDataLake`) rather than to the Open Datalake DAGs. The re-annotation DAG is
what consumes the tables these DAGs produce, so it is still needed for the full path.

Two of the 16 sources need credentials before their download DAG will run: fill in
`OPENDATALAKE_SPLICEAI_ACCESS_TOKEN` and `OPENDATALAKE_OMIM_DOWNLOAD_KEY` in
`values/airflow3-values.yaml`, which ship empty, then `helm upgrade`. Left empty, only SpliceAI and
OMIM fail, and they fail immediately with an `AirflowException` naming the missing variable. Leave
them as empty strings rather than a placeholder such as `<REPLACE_ME>` — a placeholder is sent to
the remote as a real credential and comes back as an opaque auth error instead.

### 6. Run the Open Datalake DAGs

The package defines 34 DAGs and registers 33 of them: `Open Datalake - Discover New Source Versions`
plus a download and an import DAG for each of the 16 sources (1000 Genomes, ClinVar, dbNSFP, dbSNP,
DDD, gnomAD CNV/constraint/joint/SV, HPO genes, HPO terms, MONDO, OMIM, Orphanet, SpliceAI, TOPMed
Bravo). The 34th, `- Run SQL`, is the one expected import error described in step 3.

Check the count with:
```
kubectl exec deploy/airflow-scheduler -c scheduler -- airflow dags list | grep -c opendatalake
kubectl exec deploy/airflow-scheduler -c scheduler -- airflow dags list-import-errors
```

Unpause the ones you want, then trigger `Open Datalake - Discover New Source Versions`. Each
discovered source chains download → import; the import task runs the Spark pod and writes the
Iceberg table.

**Do not run an Open Datalake import at the same time as a Radiant VCF import.** The Spark pod asks
for 2–3Gi on top of a VM that StarRocks CN, the FE and the Airflow pods have already largely
committed; running both has filled a 15.6GiB minikube to 99% and made it unresponsive to `kubectl`
and `minikube status` alike.

### 7. Read the tables from StarRocks

```sh
kubectl exec -it deploy/radiant-starrocks-fe -- mysql -P9030 -h127.0.0.1 -uroot
```
```sql
SET CATALOG opendatalake_catalog;
SHOW DATABASES;          -- reference
USE reference;
SHOW TABLES;
SELECT * FROM clinvar_v1 LIMIT 10;                 -- main branch
SELECT * FROM clinvar_v1 VERSION AS OF '20260804'; -- a version branch
```
Each `dataset_version` is an Iceberg branch named after the version, so `main` can be empty until a
release is promoted — read a specific branch with `VERSION AS OF`.

Open Datalake table names are versioned and differ from Radiant's (`clinvar_v1` vs `clinvar`,
`hpo_terms_v1` vs `hpo_term`, …). Note that `Radiant - Import Open Data` still reads
`radiant_iceberg_catalog.radiant.*`, seeded from `data/input_parquet/`; pointing it at
`opendatalake_catalog` is the pipeline-side half of SJRA-1811 and lives in `radiant-portal-pipeline`,
not in this repo.

### 8. Reading open data from the OpenDataLake

By default the sandbox reads **every** open-data source from the legacy tables
(`radiant_iceberg_catalog.radiant.*`, seeded from `data/input_parquet/`). That is what
`RADIANT_OPEN_DATA_USE_LEGACY_TABLES: "*"` in `values/airflow3-values.yaml` means, and it is why the
base install works without running a single Open Datalake DAG.

**The flag is inverted.** It names the sources to *hold back* on legacy — everything you do **not**
list is read from `opendatalake_catalog.reference.*`. So you opt a source in by *removing* it from
the list, and `"*"` (all legacy) is the most conservative setting, not an empty string. An empty
string means the opposite: every source comes from the OpenDataLake.

#### Size matters — do not enable everything

The legacy tables are a deliberately tiny sample. The OpenDataLake tables are the **real, full**
datasets, and several are far too large for a laptop minikube. They split cleanly in two:

| | Sources | Why |
|---|---|---|
| **Small — safe to enable** | `clinvar`, `mondo`, `hpo_terms`, `hpo_genes`, `orphanet`, `ddd`, `gnomad_constraint` | Gene- and term-level annotation sets. One row per gene, per term, or per clinical assertion — tens of thousands to a few million rows. |
| **Large — leave on legacy** | `dbsnp`, `dbnsfp`, `gnomad_joint`, `spliceai`, `topmed_bravo`, `1000_genomes`, `gnomad_sv` | Variant-level. One row per variant across the whole genome, so hundreds of millions of rows and, for `dbnsfp`, hundreds of columns each. Importing one of these will fill the VM. |

For scale, `clinvar_v1` — the largest of the "small" group — is about 4.2M rows, and a
`SELECT *` over it in a SQL client is already enough to exhaust a default DBeaver heap.

`omim` is small too, but its download needs `OPENDATALAKE_OMIM_DOWNLOAD_KEY` (see step 5), so leave
it on legacy unless you have the key.

#### Enabling a subset

Two things must be true before a source can be read from the OpenDataLake:

1. Its download **and** import DAGs have run, so the Iceberg table exists (step 6).
2. It is absent from `RADIANT_OPEN_DATA_USE_LEGACY_TABLES`.

To enable the recommended small set, list everything *else*:
```yaml
  - name: RADIANT_OPEN_DATA_USE_LEGACY_TABLES
    value: "1000_genomes,dbnsfp,dbsnp,gnomad_joint,gnomad_sv,omim,spliceai,topmed_bravo"
```
That leaves `clinvar`, `ddd`, `gnomad_constraint`, `hpo_genes`, `hpo_terms`, `mondo` and `orphanet`
coming from `opendatalake_catalog.reference.*`.

Apply it and re-run the consumer:
```
helm upgrade airflow apache-airflow/airflow --version 1.21.0 -f values/airflow3-values.yaml
```
Then trigger `Radiant - Re-annotate against OpenDataLake` (or `Radiant - Import Open Data` for the
plain import path).

Source names accept either spelling — the OpenDataLake contract name or the legacy table name, so
`hpo_terms` and `hpo_term` both work, as do `mondo`/`mondo_term`, `ddd`/`ddd_gene_set`,
`gnomad_joint`/`gnomad_genomes_v3`, `spliceai`/`spliceai_enriched`. A name it does not recognise
raises at parse time with the full list of valid ones, so a typo fails loudly rather than silently
leaving a source on legacy.

`RADIANT_OPEN_DATA_REF` (default `latest`) selects which Iceberg branch is read, as
`VERSION AS OF '<ref>'`. Leave it alone unless you want to pin a specific `dataset_version` —
`main` is usually empty, so an unpinned read returns no rows. Setting it to an empty string is
rejected rather than silently reading `main`.

Three sources have no OpenDataLake equivalent at all and are always legacy, whatever you set:
`ensembl_gene`, `ensembl_exon_by_gene` and `cosmic_gene_set`.

### Troubleshooting

**Open Datalake DAGs missing from the Airflow UI, with no import error.** The mount was created
after the pods started; a 9p submount does not propagate into a running container's mount namespace,
so the pod still sees the empty directory that was there at startup. `minikube ssh -- ls
/opt/airflow/dags/opendatalake` shows the files while
`kubectl exec deploy/airflow-dag-processor -c dag-processor -- ls /opt/airflow/dags/opendatalake`
is empty. The mount is fine — restart the components that consume it:
```
kubectl rollout restart deploy/airflow-dag-processor deploy/airflow-scheduler \
  statefulset/airflow-worker statefulset/airflow-triggerer
```
Confirm with the same `kubectl exec` (should list `dags` and `lib`). This is also required after
every `minikube start`, once both mounts are back up.

**Import task OOMKilled (exit 137).** Raise `OPENDATALAKE_SPARK_MEMORY`,
`OPENDATALAKE_SPARK_MEMORY_LIMIT` and `OPENDATALAKE_SPARK_DRIVER_MEMORY` together in
`values/airflow3-values.yaml` — the sandbox defaults (2Gi / 3Gi / 2g) are deliberately below the
upstream 4Gi / 6Gi / 4g because the pod competes with StarRocks in the same 12GB VM.

**`ForbiddenException: Invalid locations … is not in the list of allowed locations` at commit
time.** `OPENDATALAKE_EMR_WAREHOUSE_S3` lost its `/reference` namespace segment. Polaris validates
table locations against the *per-namespace* location it derives from `default-base-location` plus
the namespace name, not against the catalog's broader `allowedLocations`, so the value must be
`s3://opendatalake-dev/iceberg/reference`.

**404 `NoSuchBucket` on write.** The `opendatalake-dev` bucket name is hardcoded in four places that
must agree — the RustFS init job, the Polaris catalog's `allowedLocations`, the `sed` rewrite in
`docker/opendatalake-spark/Dockerfile`, and `OPENDATALAKE_RAW_BUCKET` /
`OPENDATALAKE_EMR_WAREHOUSE_S3` in `values/airflow3-values.yaml`. Each carries a `SHARED CONSTANT`
comment listing the other three.
