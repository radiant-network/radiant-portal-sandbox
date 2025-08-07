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

## Install Iceberg REST Catalog
```
kubectl apply -f k8s/iceberg-rest/
```

## Monitor Iceberg catalog pod is running (1 minutes)
```
kubectl get po | grep iceberg
```
Results 1 pod running :
```
radiant-iceberg-rest-6f488444f7-rv9gv   1/1     Running     0          17s
```

## Install locally mc (MinIO client)

On Mac :
```
brew install minio/stable/mc
mc alias set localminio http://127.0.0.1:9000 admin password
mc mirror data/input_parquet/ localminio/warehouse/input_parquet/
mc mirror data/vcf/ localminio/vcf/
```

## Init Iceberg Catalog
```
kubectl apply -f k8s/init-iceberg-catalog
```

## Monitor Iceberg Init catalog pod is completed (5 minutes the first time, due to large image pulling)
```
kubectl get po | grep init-iceberg
```
Results 1 pod completed:
```
radiant-init-iceberg-catalog-job-76vbf   0/1     Completed   0          62s
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

Checkout the radiant-portal-pipline project repository to your local workspace :
```
cd YOUR_WORKSPACE
git clone git@github.com:radiant-network/radiant-portal-pipeline.git
```

Then in a new terminal, run the following command to mount the dags directory in minikube:
```
minikube mount $(pwd)/radiant-portal-pipeline/radiant:/opt/airflow/dags/radiant
```
Let this command run in a separate terminal while you are working with Airflow.


## Install airflow volumes for logs and dags
```
kubectl apply -f k8s/airflow/
```

## Install Airflow
```
helm repo add apache-airflow https://airflow.apache.org
helm install airflow apache-airflow/airflow -f values/airflow-values.yaml
```
Took 5 minutes to install Airflow

## Monitor Airflow podd are running (5 minutes)
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
2. Trigger dag `Radiant - Init StarRocks Tables` (~ 2 minutes)
3. Trigger dag  `Radiant - Init Iceberg Tables` (~ 1 minutes)
4. Trigger dag `Radiant - Import Open Data` (~ 5 minutes)
   - In raw_rcv_filepaths, set the value `s3://warehouse/input_parquet/clinvar_rcv_summary/*.json`
5. Trigger dag `Radiant - Scheduled Import` (~ 5 minutes)


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
- Usernane: `user1` (or any username you want)
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
