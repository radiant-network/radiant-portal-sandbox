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

## Install minikube metrics-server (optional)
```
minikube addons enable metrics-server
```

## Install minio
```
kubectl apply -f k8s/minio/
```

## Monitor Minio pod are running (1 minutes)
```
k get po | grep minio
```

## Install postgres
```
kubectl apply -f k8s/postgres/
```

## Monitor Postgres pod are running (1 minutes)
```
k get po | grep postgres
```

## Install Iceberg REST Catalog
```
kubectl apply -f k8s/iceberg-rest/
```

## Monitor Iceberg catalog pod are running (1 minutes)
```
k get po | grep iceberg
```

## Install locally mc (minio client)

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

## Monitor Iceberg Init catalog pod are completed (5 minutes the first time, due to large image pulling)
```
k get po | grep iceberg
```

## Install Starrocks
```
kubectl apply -f k8s/starrocks/
```

## Monitor Starrocks pod are running (5 minutes the first time, due to large image pulling)
```
k get po | grep starrocks
```

## Install keycloak
```
kubectl apply -f k8s/keycloak/
```

## Install API
```
kubectl apply -f k8s/api/
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

## Mount volume for dags in minikube
```
minikube mount YOUR_WORKSPACE/radiant-portal-pipeline/radiant:/opt/airflow/dags/radiant
```


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

## Configure airflow
Connect to the Airflow UI at http://localhost:8080
- Username: airflow
- Password: airflow

Then Activate all the dags by sliding the toggle button of each dag to the right.

Configure the pools :
- Go to Admin -> Pools
- Create a new pool named "import_part" with 1 slot
- Create a new pool named "import_vcf" with 128 slots

## Run dags
- Run dag [QA] Radiant - Init Simulated Clinical Data
  - Set vcf_bucket_prefix to s3://vcf
- Run dag Radiant - Init StarRocks Tables (~ 10 minutes)
- Run dag  Radiant - Init Iceberg Tables (~ 2 minutes)
- Run dag Radiant - Import Open Data (~ 10 minutes)
  - In raw_rcv_filepaths, set the value s3://warehouse/input_parquet/clinvar_rcv_summary/*.json
- Run dag Radiant - Scheduled Import (~ 10 minutes)


## Edit /etc/host file 
Add the following line to your /etc/hosts file to access the keycloak admin console:
```
127.0.0.1  radiant-keycloak
```

## Create user in keycloak 
Log into keycloak admin console for creating a user
http://radiant-keycloak:8282/
Username : admin
Password : admin

Click on Manage Realms, then click on Radiant

Click on Users, then click on Create a new User

- Email verified : ON
- Usernane: user1 (or any username you want)
- Email: user1@email.me (or any email you want)
- First Name: User1 (or any first name you want)
- Last Name: Test (or any last name you want)

Click on Create button

Click on Credentials tab, then click on Set Password

- Password: user1 (or any password you want)
- Password confirmation: user1 (or any password you want)
- Temporary: OFF
- Confirm by clicking on Save Password

Click on Role Mappings tab

Click on Assign Roles. then select Client Roles

Select radiant in the table and then click on Assign Button

Open a new browser tab and go to http://localhost:3000

You should be redirect to keycloak login page. Put the username and password you just created.
Then you should be able to see the case list page.

If you click on Case 1 (Family trio) or case 8 (Solo) you should be able to click on Variants tab and see the variants for the case.
