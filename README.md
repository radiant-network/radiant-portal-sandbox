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
- 12 GB RAM
- 30 GB Disk Space
- 4 CPU Cores

Configure Docker to use at least 12 GB of RAM and 4 CPU Cores.

Note: if you change docker configuration, you need to delete your minikube.

Configure minikube to use at least 12 GB of RAM and 4 CPU Cores:
```
minikube config set memory 12000
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

## Install MinIO
```
kubectl apply -f k8s/minio/
```

## Monitor Minio pods are running (1 minutes)
```
kubectl get po | grep minio
```
Results 1 pod running and 1 pod completed:
```
radiant-minio-bucket-init-job-2znb9   0/1     Completed   0          103s
radiant-minio-d7cf486cf-22zlg         1/1     Running     0          103s
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

## Install locally mc (MinIO client)

On Mac :
```
brew install minio/stable/mc
mc alias set localminio http://127.0.0.1:9000 admin password
mc mirror data/input_parquet/ localminio/warehouse/input_parquet/
mc mirror data/vcf/germline localminio/vcf/
mc mirror data/vcf/somatic localminio/vcf/
```

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

**Important note:** Ensure the image's name and tag matches with the `RADIANT_TASK_OPERATOR_IMAGE` from the `values/airflow-values.yaml` file.

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

## Run dags
Trigger the following dags in order. Each dag takes a few minutes to run. Wait for each dag to complete before triggering the next one.
1. Trigger dag `[QA] Radiant - Init Simulated Clinical Data`
   - Set vcf_bucket_prefix to `s3://vcf`
2. Trigger dag `Radiant - Init StarRocks Base Tables` (~ 2 minutes)
3. Trigger dag  `Radiant - Init Iceberg Tables` (~ 1 minutes)
4. Trigger dag `Radiant - Import Open Data` (~ 5 minutes)
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

(Ignore this section if you are not testing the OpenDataLake → Radiant ETL integration, SJRA-1811)

The unified sandbox runs the [radiant-open-datalake](https://github.com/radiant-network/radiant-open-datalake)
ETL **inside this stack** rather than as a separate minikube: it reuses the MinIO, Postgres, Polaris,
StarRocks and Airflow installed above, all in the `radiant` namespace. The Open Datalake ETL writes
Iceberg tables into their own Polaris catalog (`opendatalake`, namespace `reference`), and StarRocks
attaches them as the external catalog `opendatalake_catalog`, so Radiant's open-data DAG can read
them.

```
radiant-open-datalake DAGs (in the same Airflow)
   └─> Spark pod (spark-submit --master local[*])
         ├── raw in:  s3://opendatalake-dev/raw/landing/<source>/<version>   (MinIO)
         └── out:     Polaris catalog `opendatalake` -> s3://opendatalake-dev/iceberg/reference
                          └─> StarRocks external catalog `opendatalake_catalog`
                                └─> Radiant - Import Open Data
```

Prerequisite: the `radiant-open-datalake` repository checked out next to this one.
```
cd YOUR_WORKSPACE
git clone git@github.com:radiant-network/radiant-open-datalake.git
```

### Bucket, Polaris catalog and StarRocks catalog

These ship with the manifests already applied above, so a fresh install needs nothing extra:
- `k8s/minio/radiant-minio-bucket-init-job.yaml` creates the `opendatalake-dev` bucket.
- `k8s/polaris/init/radiant-polaris-init-opendatalake-catalog-job.yaml` creates the Polaris catalog
  `opendatalake` (warehouse `s3://opendatalake-dev/iceberg`) and the `reference` namespace.
- `k8s/starrocks/radiant-starrocks-opendatalake-catalog-job.yaml` creates the StarRocks external
  catalog `opendatalake_catalog`.

On an **existing** sandbox, apply just the new pieces and re-run the finished jobs:
```
kubectl delete job radiant-minio-bucket-init-job
kubectl apply -f k8s/minio/
kubectl apply -f k8s/polaris/init/
kubectl apply -f k8s/starrocks/
```

Verify:
```
kubectl get po | grep -E "opendatalake|bucket-init"
mc ls localminio/opendatalake-dev
kubectl exec -it deploy/radiant-starrocks-fe -- mysql -P9030 -h127.0.0.1 -uroot -e "SHOW CATALOGS;"
```
`SHOW CATALOGS` should list `radiant_iceberg_catalog`, `radiant_jdbc` and `opendatalake_catalog`.

### Build the Open Datalake images

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

### Apply the sandbox operator swaps

The Open Datalake DAGs target AWS (ECS for downloads, EMR Serverless for Spark). Swap both for the
in-cluster Kubernetes equivalents. The versions in `opendatalake/operators/` are this sandbox's
variants — they use the `radiant` namespace, `radiant-minio` and `radiant-polaris`, unlike the ones
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
`spark_k8s.py` only implements JAR mode (`--class <entry_class> <jar>`). The other 33 opendatalake
DAGs are unaffected. To silence the banner, either set the six `OPENDATALAKE_EMR_*` variables it
names to dummy values in `values/airflow3-values.yaml` (the DAG then parses but still cannot run
without EMR), or leave it as-is.

### Mount the Open Datalake DAGs

In a new terminal, alongside the `radiant` mount already running:
```
minikube mount $(pwd)/radiant-open-datalake/airflow/opendatalake:/opt/airflow/dags/opendatalake
```
The package is mounted *under* the DAGs folder (not as the DAGs folder) so the DAG files'
`from opendatalake... import` statements resolve — `/opt/airflow/dags` is on `PYTHONPATH` and must
contain the `opendatalake/` package root. Leave this running like the `radiant` mount.

**Start this mount before installing or upgrading Airflow.** The pods bind-mount
`/opt/airflow/dags` at startup, and a 9p submount created *afterwards* does not propagate into a
running container's mount namespace — the pod keeps seeing the empty directory that was there when
it started, while `minikube ssh -- ls /opt/airflow/dags/opendatalake` shows the files. The symptom
is opendatalake DAGs missing from the UI with **no import error**, because the processor never sees
the files at all. If that happens, the mount is fine; just restart the components that mount it:
```
kubectl rollout restart deploy/airflow-dag-processor deploy/airflow-scheduler \
  statefulset/airflow-worker statefulset/airflow-triggerer
```
Confirm with `kubectl exec deploy/airflow-dag-processor -c dag-processor -- ls /opt/airflow/dags/opendatalake`
(should list `dags` and `lib`, not be empty).

### Airflow

The Open Datalake env vars are already in `values/airflow3-values.yaml`. If Airflow is running,
pick them up with:
```
helm upgrade airflow apache-airflow/airflow --version 1.21.0 -f values/airflow3-values.yaml
```

No Airflow image rebuild is needed: the Open Datalake DAGs import `airflow.providers.amazon`, which
the base image already bundles at the version `constraints-python3.12.txt` pins.

Then create the pools (Admin → Pools), 1 slot each:
- `opendatalake_download_tasks_pool`
- `opendatalake_direct_upload_tasks_pool`
- `opendatalake_import_tasks_pool`

Two sources need credentials before their download DAG will run: fill in
`OPENDATALAKE_SPLICEAI_ACCESS_TOKEN` and `OPENDATALAKE_OMIM_DOWNLOAD_KEY` in
`values/airflow3-values.yaml`, which ship empty. Left empty, only those two sources fail, and they
fail immediately with an `AirflowException` naming the missing variable.

### Run the Open Datalake DAGs

Unpause the `opendatalake` DAGs you want, then trigger
`Open Datalake - Discover New Source Version`. Each discovered source chains download → import; the
import task runs the Spark pod and writes the Iceberg table.

Browse the result from StarRocks:
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
