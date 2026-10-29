# Radiant Portal Sandbox

This project is a sandbox for installing Radiant portal stack components locally. 

It is ONLY intended to be used for testing and development purposes, allowing users to experiment with the Radiant portal stack.

# Requirements
Software requirements to run this project locally:
- Docker
- Minikube 
- Kubectl
- Helm
- AWS CLI v2.22+ (`brew install awscli`), to seed the buckets

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
minikube config set container-runtime docker
```

4 CPUs is the minimum, and an import saturates them. If Docker has more to give, set `cpus 6`
instead (see [Configure airflow](#configure-airflow) for what keeps an import working on 4).

**The container runtime must be `docker`.** Every image in this sandbox is built with
`eval $(minikube docker-env) && docker build …`, which needs a real Docker Engine inside the VM.
With the `containerd` runtime, `docker-env` points at a compatibility shim and every build fails with:
```
ERROR: failed to build: failed to inspect pulled image moby/buildkit:buildx-stable-1: Error response from daemon: 404 page not found
```
Check the `RUNTIME` column of `minikube profile list`. These settings only apply when the cluster is
created, so changing them on an existing cluster means `minikube delete && minikube start`, which
wipes all volumes.

# Installation

Unless a step says otherwise, run every command from the root of this repository.


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

None of the manifests set a namespace, so they land in whatever namespace kubectl points at.
`minikube start` and `minikube update-context` reset it to `default`. If `kubectl get po` suddenly
shows nothing, check with `kubectl config view --minify -o jsonpath='{..namespace}'` and run the
command above again. Never `kubectl apply` while pointed at `default`.

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
`--endpoint-url` flags with a profile you do not want to keep.

Run the exports **in the same terminal as the `aws` commands**, not in the `minikube tunnel` one.
They only last for that shell, so repeat them in any new terminal. Don't put them in `~/.zshrc`,
or every `aws` command would go to the local RustFS instead of AWS. The pods get the same
credentials from their manifests, but the seed runs on your machine because `data/` is on your
disk, and from the host RustFS is `127.0.0.1:9000` (through the tunnel), not `radiant-rustfs:9000`.
```
export AWS_ACCESS_KEY_ID=admin
export AWS_SECRET_ACCESS_KEY=password
export AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL=http://127.0.0.1:9000

aws s3 sync data/input_parquet/ s3://warehouse/input_parquet/
aws s3 sync data/vcf/germline/ s3://vcf/
aws s3 sync data/vcf/somatic/ s3://vcf/
aws s3 sync data/gene_panels/ s3://warehouse/gene_panels/ --exclude "*.md"
```

Verify — expect 35 objects under `warehouse/input_parquet/`, 20 under `vcf/` and 1 under
`warehouse/gene_panels/` (see [data/gene_panels/README.md](data/gene_panels/README.md) to load it in the portal):
```
aws s3 ls --recursive s3://warehouse/input_parquet/ | wc -l
aws s3 ls --recursive s3://vcf/ | wc -l
aws s3 ls --recursive s3://warehouse/gene_panels/ | wc -l
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

## Install Ranger (optional)

The API and the toolbox commands (`create-user`, `create-tenant`, `refresh-tenants`) call the Ranger
admin API when they provision users, tenant roles and PII masking policies. Ranger is optional:
skip this step and the rest of the stack works the same, browsing cases and variants included. Only
the Ranger step of those operations fails, **after** their other work is done:

| Without Ranger | What still happens | What fails |
|---|---|---|
| Adding a member in the portal | Keycloak user, StarRocks user and portal roles are created | the request returns a 500 |
| `create-user` | same as above | exits with an error |
| `refresh-tenants` | tenant views and gene panel MVs are refreshed | masking policies |

The error then reads `ranger: … dial tcp …:6080: connect: connection refused` (or `no such host`).
Install Ranger if you work on user or tenant administration, or want those operations to succeed.

The image is the one radiant-portal's local stack uses, run as a single pod. It creates its own
`ranger` database and `rangeradmin` role in the sandbox Postgres, so install it after Postgres.
```
kubectl apply -f k8s/ranger/
```

The policies are created in Ranger but **not enforced**: StarRocks keeps its native access control,
so queries are neither masked nor filtered.

## Monitor Ranger pod is running (3 minutes)
```
kubectl get po | grep ranger
kubectl logs deploy/radiant-ranger | grep register
```
Results 1 pod running, and the `starrocks` service registered:
```
radiant-ranger-84f496dd7-qk87k           1/1     Running     0          3m29s
[register] service-def 'starrocks' created (from starrocks.json)
[register] service 'starrocks' created (from starrocks.json)
```

The Ranger console is at http://localhost:6080 (`admin` / `rangerR0cks!`). The pod takes about
1 GiB of memory. If the VM runs short during a large import, scale it down meanwhile with
`kubectl scale deploy/radiant-ranger --replicas=0`.

## Install API
```
kubectl apply -f k8s/api/
```

This also starts `radiant-cli-grant-job`: once the API has applied its migrations, it grants the
`radiant-cli` service account (Airflow's `radiant_api_conn`) the `tenant_admin` role and the `data_manager`
role at every organization (`*`) in tenant `radiant`.

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

Despite the name, the task and dbt "operators" are not Kubernetes operators. They are the images
of the short-lived pods that Airflow starts for heavy tasks (`KubernetesPodOperator`): the task
operator runs the Radiant VCF/Iceberg code, and the dbt operator runs the data integrity checks
against StarRocks. Pods use `imagePullPolicy: IfNotPresent`, so the image must already be in
Minikube's Docker with the exact tag from `values/airflow3-values.yaml`.

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

## Pre-building the Radiant toolbox image and secret

The `Radiant - Toolbox` DAG (`create-tenant`, `create-user`, `refresh-tenants`) launches a pod from
the radiant-portal backend's toolbox image. It is not pullable from ghcr, so build it locally.
From this repository, with `radiant-portal` cloned next to it:

```
eval $(minikube -p minikube docker-env)  # To ensure the image is built inside minikube's docker environment
docker build -t radiant-local-toolbox:latest \
  -f ../radiant-portal/backend/toolbox.Dockerfile ../radiant-portal/backend
```

The tag must match `RADIANT_TOOLBOX_OPERATOR_IMAGE` in `values/airflow3-values.yaml`.

Then apply the secret the pod reads its StarRocks and Postgres settings from:

```
kubectl apply -f k8s/toolbox/
```

> `refresh-tenants`, `create-tenant` and `create-user` also write to Ranger. Without it (see
> [Install Ranger (optional)](#install-ranger-optional)) they fail at their Ranger step, once the
> rest of their work is done.

> **Testing the Open Data Lake integration?** Build its two images now as well, and apply the
> operator swaps — both before the Airflow install below. See
> [Open Data Lake integration](#open-data-lake-integration).

## Install airflow volumes for logs and dags
```
kubectl apply -f k8s/airflow/
```

## Install Airflow

Before installing, check that:
- the task operator, dbt operator and toolbox images are built (`eval $(minikube -p minikube docker-env) && docker images | grep radiant`);
- the Airflow volumes above are applied;
- the DAG mount (and the Open Data Lake one, if you use it) is running in its own terminal;
- the `apache-airflow` Helm repository is added (once per machine, otherwise `helm install` fails
  with `repo apache-airflow not found`):
  ```
  helm repo add apache-airflow https://airflow.apache.org
  helm repo update apache-airflow
  ```

- Build the docker image, from the root of this repository. The tag must be the `images.airflow.tag`
  value in `values/airflow3-values.yaml`: the chart pulls with `IfNotPresent`, so any other tag is not
  found, and reusing an old tag keeps the old image. Use a new tag after you change `docker/airflow3/`.
  ```
  TAG=<images.airflow.tag from values/airflow3-values.yaml>
  eval $(minikube -p minikube docker-env)
  docker build -t ghcr.io/radiant-network/radiant-airflow3:$TAG docker/airflow3
  ```
- Install via helm, still from the root of this repository (`values/` is a path relative to it):
  ```
  helm install airflow apache-airflow/airflow --version 1.21.0 -f values/airflow3-values.yaml
  ```

Took 5 minutes to install Airflow

If the install fails or times out (for example `ImagePullBackOff` because an image was not built
yet), fix the cause and run `helm upgrade` with the same arguments rather than `helm install` again.
The Airflow user is created by a post-install hook, so a failed install leaves no user and every
login is rejected until the upgrade re-runs the hook.

## Monitor Airflow pod are running (5 minutes)
```
kubectl get po | grep airflow
```
Results 7 pods running:
```
airflow-api-server-54f7b86969-fkwh6      1/1     Running     0          5m
airflow-dag-processor-6dfd88894-sd2dq    2/2     Running     0          5m
airflow-redis-0                          1/1     Running     0          5m
airflow-scheduler-9ff6fdb7f-wwphn        2/2     Running     0          5m
airflow-statsd-5c5bdd47c5-4lkhf          1/1     Running     0          5m
airflow-triggerer-0                      2/2     Running     0          5m
airflow-worker-0                         2/2     Running     0          5m
```

## Configure airflow
Connect to the Airflow UI at http://localhost:8080
- Username: airflow
- Password: airflow

Then Unpause all the dags by sliding the toggle button of each dag to the right.

Don't skip the ones you never trigger yourself. `Radiant - Scheduled Import` (`radiant-import`)
triggers `radiant-import-part`, which triggers `radiant-import-snv-vcf`, then
`radiant-data-integrity-starrocks`, and waits for each. A paused child leaves its run `queued` until
the parent times out and fails at `import_part`. None of them has a schedule, so unpausing them
triggers nothing:
```
kubectl exec deploy/airflow-scheduler -c scheduler -- sh -c \
  'for d in radiant-import radiant-import-part radiant-import-snv-vcf radiant-data-integrity-starrocks; do airflow dags unpause $d -y; done'
```

Configure the pools :
- Go to Admin -> Pools
- Create a new pool named "import_part" with 1 slot
- Create a new pool named "import_vcf" with 2 slots (see below)
- Create a new pool named "starrocks_insert_pool" with 1 slot **and "Include deferred tasks"
  ticked** — see below

Only if you are testing the Open Data Lake integration, create these three as well, 1 slot each
(plain pools — they do *not* need "Include deferred tasks"):
- `opendatalake_download_tasks_pool`
- `opendatalake_direct_upload_tasks_pool`
- `opendatalake_import_tasks_pool`

`import_vcf` caps how many VCF extraction pods run at once. Deployed environments use 128; keep
2 here. Each pod requests 500m CPU with no limit, and pyarrow/cyvcf2 use every core they get, so
with 128 slots the five sample pods start together on 4 CPUs. The load then passes 13 (it reaches
23 during the StarRocks inserts), Airflow's own liveness probes time out, and the kubelet restarts
the scheduler and worker mid-import, which fails every extraction task. With 2 slots the extraction
takes about 8 minutes. With 6 CPUs there is more headroom, but keep the pool small.

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
  airflow pools set import_vcf 2 "VCF import fan-out (2 in the sandbox: 4 CPUs)"
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
   - Set `udf_release_version` to `v2.0.0`. **Do not keep the default `v1.2.0`** (see below).
3. Trigger dag  `Radiant - Init Iceberg Tables` (~ 1 minutes)
4. Trigger dag `Radiant - Import Open Data` (~ 5 minutes)
   - Leave `skip_legacy_tables` unchecked.
   - In raw_rcv_filepaths, set the value `s3://warehouse/input_parquet/clinvar_rcv_summary/*.json`
   - In cytoband_filepath, set the value `s3://warehouse/input_parquet/cytoband/*.txt.gz`
5. Trigger dag `Radiant - Scheduled Import` (~ 5 minutes)

The last step of Radiant - Scheduled Import will fail — this is expected: it triggers Radiant - Data Integrity Checks, which flags the (deliberately imperfect) sandbox test data.

### `udf_release_version` must be `v2.0.0`

`Init StarRocks Base Tables` installs the StarRocks UDFs `GET_VARIANT_ID` and `GET_CNV_ID` from
[radiant-starrocks-udf](https://github.com/radiant-network/radiant-starrocks-udf) releases. The
CNV insert now passes the resolved CNV type (`LOSS`, `GAIN`) to `GET_CNV_ID`, which only v2.0.0
understands; v1.2.0 only knows the VCF alternate (`<DEL>`) and returns `NULL` for `LOSS`. The DAG
still defaults to `v1.2.0`, so with the default the germline CNV insert fails with:
```
Insert has filtered data ... NULL value in non-nullable column 'cnv_id'
```
(read the rejected rows with the `select tracking_log from information_schema.load_tracking_logs
where job_id=...` query printed in the task log). v2.0.0 changes nothing for `GET_VARIANT_ID`.

To fix an already-initialised sandbox without re-running the DAG, replace the function with the
DAG's own statement (`radiant-portal-pipeline/radiant/dags/sql/radiant/init/cnv_id_udf.sql`), then
clear the failed import tasks:
```
kubectl exec -i deploy/radiant-starrocks-fe -- mysql -h127.0.0.1 -P9030 -uroot <<'SQL'
CREATE OR REPLACE GLOBAL FUNCTION GET_CNV_ID (string, bigint, bigint, string) RETURNS bigint
PROPERTIES (
  "symbol" = "org.radiant.CNVIdUDF",
  "type" = "StarrocksJar",
  "file" = "https://github.com/radiant-network/radiant-starrocks-udf/releases/download/v2.0.0/radiant-starrocks-udf-2.0.0-jar-with-dependencies.jar"
);
SQL
# Must return two ids, not NULL
kubectl exec deploy/radiant-starrocks-fe -- mysql -h127.0.0.1 -P9030 -uroot -N -e \
  "SELECT GET_CNV_ID('1', 4063594, 1199, 'LOSS'), GET_CNV_ID('1', 13224579, 17455, 'GAIN')"
```

### Expected failure: mark the somatic CNV of case TCRBOA6 as success

The simulated clinical data (`radiant-portal-pipeline/radiant/dags/sql/clinical/seeds.sql`)
references `s3://vcf/TCRBOA6_SRX1166091-T.cnv.vcf.gz` (and its `.tbi`). That file is known to be
problematic and is deliberately not shipped in `data/vcf/`, so `import_somatic_cnv_vcf_k8s` fails
with `S3DownloadError … 404`. Because `radiant-import-part` waits for every VCF import, **nothing**
is inserted into StarRocks until that task is resolved.

This is the expected procedure, confirmed by the team: mark the task as success by hand.
1. In the Airflow UI, open `radiant-import-part` and select the failed run.
2. Click the `import_somatic_cnv_vcf_k8s` task and mark it **Success**, for that task only. Do
   **not** tick "Downstream": that would mark the waiting insert tasks as success without running
   them, and nothing would reach StarRocks.
3. Then clear the run's remaining failed tasks (the `upstream_failed` inserts) so they run: on the
   run, **Clear → Only failed**.

Everything except that one somatic CNV gets imported.

The same from the CLI, for scripting:
```
RUN='<run_id of the failed radiant-import-part run>'
kubectl exec deploy/airflow-scheduler -c scheduler -- python -c "
from airflow.models import TaskInstance as TI
from airflow.utils.session import create_session
with create_session() as s:
    ti = s.query(TI).filter(TI.dag_id=='radiant-import-part', TI.run_id=='$RUN',
                            TI.task_id=='import_somatic_cnv_vcf_k8s').one()
    ti.state = 'success'; s.merge(ti)"
# then, with the run's logical date (shown by `airflow dags list-runs radiant-import-part`):
kubectl exec deploy/airflow-scheduler -c scheduler -- airflow tasks clear radiant-import-part \
  --only-failed --start-date <logical_date> --end-date <logical_date> --yes
```

To re-run only what failed in an import (for example after fixing the UDF), use the same
`airflow tasks clear … --only-failed` call; add `--downstream` when the failed tasks are upstream
of others. Triggering a new `Radiant - Scheduled Import` instead may find nothing left to import,
since the failed run already took the sequencing experiments.

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

## Give the user roles in the portal

A Keycloak account alone only gets you to a 403 page, "Vous n'avez pas accès à RADIANT": the portal
is multi-tenant and reads each user's roles from the `user_role` table of the `radiant` Postgres
database. Grant them with the toolbox's `create-user`, using the user's Keycloak ID (*Users* → the
user → *ID*):
```
SUB=<keycloak user id>
kubectl run create-user --rm -i --restart=Never --image=radiant-local-toolbox:latest \
  --overrides='{"spec":{"containers":[{"name":"create-user","image":"radiant-local-toolbox:latest",
    "imagePullPolicy":"Never","envFrom":[{"secretRef":{"name":"radiant-toolbox-secret"}}],
    "command":["create-user","-sub","'"$SUB"'",
      "-grant","radiant:*:member","-grant","radiant:*:geneticist",
      "-grant","radiant:*:data_manager","-grant","radiant::tenant_admin"]}]}}'
```
A grant is `tenant:org:role`; `*` means every organization of the tenant, and an empty org a
tenant-wide role. `member` lets the user search cases, `geneticist` interpret variants,
`data_manager` import data, and `tenant_admin` manage members. Without Ranger the command ends with
a `ranger: …` error after the roles are granted (see [Install Ranger (optional)](#install-ranger-optional)).

Once a user has `tenant_admin`, further members can be added from the portal's admin section. They
get no password: set one in the Keycloak console (*Credentials* → *Set password*, *Temporary* off).

## Connect to Radiant Portal UI
Open a new browser tab and go to http://localhost:3000

You should be redirected to keycloak login page. Put the username and password you just created.
Then you should be able to see the case list page.

If you click on Case 1 (Family trio) or case 8 (Solo), you should be able to click on Variants tab and see the variants for the case.

## After a restart or laptop sleep

Putting the laptop to sleep can leave the cluster unresponsive: Docker Desktop restarts the
`minikube` container on new host ports, but the kubelet does not come back. `minikube status` shows:
```
kubelet: Stopped
apiserver: Stopped
kubeconfig: Misconfigured
```
Run `minikube start` (not `minikube delete`, which wipes all volumes). Pods show `Error` for a few
minutes after any restart, then recover on their own.

After every `minikube start`, whether after sleep or not, redo these steps in order:
1. Point kubectl back at the namespace: `kubectl config set-context --current --namespace=radiant`.
2. Stop the old `minikube tunnel` and `minikube mount` processes with Ctrl+C, then start them again,
   each in its own terminal. They keep running after a restart but no longer work.
3. Restart the Airflow pods, which started before the mounts existed and see an empty DAG folder:
   ```
   kubectl rollout restart deploy/airflow-dag-processor deploy/airflow-scheduler \
     statefulset/airflow-worker statefulset/airflow-triggerer
   ```

## Browsing the data

Polaris has no web UI: port 8181 serves the Iceberg REST and management APIs, and port 8182 serves
health and metrics (`/q/health`, `/q/metrics`). To look at the data:
- **StarRocks**, with any MySQL client (DBeaver, `mysql`): `localhost:9030`, user `root`, no
  password. With DBeaver's MySQL driver, set the driver properties `allowPublicKeyRetrieval=true`
  and `useSSL=false`. The Iceberg tables in Polaris are only reachable through SQL, not the
  navigator tree:
  ```
  SHOW CATALOGS;
  SHOW TABLES FROM radiant_iceberg_catalog.radiant;
  ```
- **Postgres**: `localhost:5432`, `postgres` / `postgres`. In DBeaver, tick *Show all databases* to
  see `airflow`, `radiant`, `polaris` and `keycloak`.
- **RustFS console** (files behind the tables): http://localhost:9001, `admin` / `password`.
- **Polaris API** with `curl`. Every call needs the `Polaris-Realm: radiant` header:
  ```
  TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
    -H "Polaris-Realm: radiant" -d grant_type=client_credentials \
    -d client_id=root -d client_secret=password -d scope=PRINCIPAL_ROLE:ALL | jq -r .access_token)
  curl -s -H "Authorization: Bearer $TOKEN" -H "Polaris-Realm: radiant" \
    http://localhost:8181/api/catalog/v1/polaris/namespaces/radiant/tables | jq
  ```

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
