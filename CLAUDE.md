# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo is a **local sandbox** for installing and testing the Radiant portal stack on Minikube. It contains no application source — only Kubernetes manifests, Helm values, Dockerfiles, and seed data used to stand up the full stack for development and QA. Application code (API, worker, UI, DAGs) lives in sibling repos; this sandbox deploys their published images.

The companion repo `radiant-portal-pipeline` (cloned separately by the user) provides Airflow DAGs and the source for the `radiant-airflow-task-operator` image. Several install steps in the README depend on that repo being checked out next to this one.

## Stack layout

The stack is brought up component-by-component, in a fixed order, because later components depend on earlier ones being healthy. Follow the install order in the README.


## Common operations

```bash
# Always run in a separate terminal first
minikube tunnel

# Namespace setup (one-time)
kubectl create namespace radiant
kubectl config set-context --current --namespace=radiant

# Apply a component (replace <component>)
kubectl apply -f k8s/<component>/

# Watch a component come up
kubectl get po | grep <component>

# Copy files to minio
mc alias set localminio http://127.0.0.1:9000 admin password
mc mirror <src_folder> <dst_s3_url>

# Build images inside Minikube's docker (so kubelet can find them without a registry push)
eval $(minikube -p minikube docker-env)
docker build -t <tag> -f <Dockerfile> .
```

There is no test suite, lint, or build step at the repo level — changes are validated by re-applying manifests and observing pod state.

## Editing guidance

- **Manifests are the contract.** Most changes here are tweaks to YAML in `k8s/*/` or to Helm values in `values/`. Image tags and env vars (e.g. `RADIANT_TASK_OPERATOR_IMAGE`, `RADIANT_AUTHORIZATION_PROVIDER`) are the most common knobs.
- **Don't change install order** unless you also change the dependency assumptions baked into init jobs (e.g. `polaris-init-tables` assumes MinIO + Postgres + Polaris deploy are up).
- **Airflow 2/3 parity:** any DAG-affecting or operator-image change must be checked against both `values/airflow2-values.yaml` and `values/airflow3-values.yaml`, since both are supported
- **Resetting:** if Docker resource config changes, the Minikube VM must be deleted and recreated — config drift between Docker and Minikube is a known foot-gun.

## OpenFGA (optional)

`values/openfga-values.yaml` installs OpenFGA in-memory (data lost on pod restart — fine for sandbox, not prod). Switching the API to OpenFGA also requires creating a Keycloak client (named after the project, e.g. `CBTN`) with `geneticist` and `requester` roles, then assigning roles to users so the JWT carries the right `resource_access` claim. The README has the full Keycloak click-path.
