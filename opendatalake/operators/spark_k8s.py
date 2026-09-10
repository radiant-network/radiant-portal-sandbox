"""Sandbox-only drop-in replacement for the Open Datalake EMR Serverless import operator.

This is the radiant-portal-sandbox variant of
`radiant-open-datalake/airflow/sandbox/operators/spark_k8s.py`: same operator, retargeted at the
unified sandbox, where the Open Datalake ETL shares the Radiant stack's namespace (`radiant`),
MinIO (`radiant-minio`) and Polaris (`radiant-polaris`) instead of running its own copies in an
`opendatalake` namespace.

Runs the Open Datalake Spark ETL as `spark-submit --master local[*]` inside a
KubernetesPodOperator, reading raw files from the in-cluster MinIO (via Hadoop S3A) and writing
Iceberg tables through the in-cluster Apache Polaris REST catalog.

Keeps the class name `EmrServerlessJobOperator` so switching the DAG only rewrites the import path
(`operators.emr` -> `operators.spark_k8s`). EMR-only kwargs (waiter_*, deferrable, ...) are accepted
and ignored. Do NOT commit the swap into radiant-open-datalake: this operator has no place in the
AWS deployment.

UPSTREAM CONTRACT -- this file is a fork and nothing here is imported or linted by this repo, so
drift only shows up as a DAG-parse error in the sandbox. It depends on, and must be re-checked
against, `radiant-open-datalake/airflow/`:

    opendatalake.lib.operators.emr.job_name_timestamp   imported below
    opendatalake.dags.import_source.build_import_operator
        passes entry_point_arguments, task_id, task_display_name, pool, name,
        and optionally spark_conf / waiter_max_attempts
    sandbox/operators/spark_k8s.py                      the file this mirrors

Only constants differ from that mirror: namespace, MinIO/Polaris service names, the Polaris
credential and scope, the added Polaris-Realm header, and the pod resources. The durable fix is to
push this env-var parameterisation upstream and delete this copy; until then, re-diff the two files
whenever the Open Datalake operators change.

Install into the radiant-open-datalake checkout with:

    cp opendatalake/operators/spark_k8s.py \
       ../radiant-open-datalake/airflow/opendatalake/lib/operators/spark_k8s.py
    sed -i '' 's/operators\\.emr/operators\\.spark_k8s/g' \
       ../radiant-open-datalake/airflow/opendatalake/dags/import_source.py
"""

import os

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s

from opendatalake.lib.operators.emr import job_name_timestamp  # noqa: F401

DEFAULT_ENTRY_CLASS = "org.radiant.opendatalake.ImportPublicTable"
SPARK_IMAGE = os.getenv("OPENDATALAKE_SPARK_IMAGE", "ghcr.io/radiant-network/opendatalake-spark:latest")
JAR_PATH = "/opt/app/radiant-open-datalake-spark.jar"

# Namespace of the unified sandbox -- the Radiant stack's namespace, not `opendatalake`.
NAMESPACE = os.getenv("OPENDATALAKE_SPARK_NAMESPACE", "radiant")

# In-cluster endpoints, shared with the Radiant stack.
MINIO_ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://radiant-minio:9000")
POLARIS_URI = os.getenv("OPENDATALAKE_POLARIS_URI", "http://radiant-polaris:8181/api/catalog")
POLARIS_REALM = os.getenv("OPENDATALAKE_POLARIS_REALM", "radiant")
POLARIS_CREDENTIAL = os.getenv("OPENDATALAKE_POLARIS_CREDENTIAL", "root:password")

# Extra classpath dir baked into the image; holds config/dev.conf (see
# docker/opendatalake-spark/Dockerfile).
_CONF_EXTRA_CLASSPATH = "/opt/app/conf-extra"

# Spark conf for the sandbox: raw reads via S3A against MinIO, Iceberg writes via Polaris.
_LOCAL_SPARK_CONF = {
    # --- raw input: Hadoop S3A -> MinIO ---
    "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
    "spark.hadoop.fs.s3a.path.style.access": "true",
    "spark.hadoop.fs.s3a.access.key": "admin",
    "spark.hadoop.fs.s3a.secret.key": "password",
    "spark.hadoop.fs.s3a.endpoint": MINIO_ENDPOINT,
    "spark.hadoop.fs.s3a.endpoint.region": "us-east-1",
    # --- Iceberg output: Polaris REST catalog (metadata) + direct MinIO S3 access (data) ---
    "spark.sql.catalog.opendatalake.type": "rest",
    "spark.sql.catalog.opendatalake.uri": POLARIS_URI,
    "spark.sql.catalog.opendatalake.warehouse": "opendatalake",
    "spark.sql.catalog.opendatalake.credential": POLARIS_CREDENTIAL,
    # radiant-polaris grants CATALOG_MANAGE_CONTENT to catalog_admin (see polaris-init.sh), so ask
    # for that scope rather than PRINCIPAL_ROLE:ALL.
    "spark.sql.catalog.opendatalake.scope": "PRINCIPAL_ROLE:CATALOG_MANAGE_CONTENT",
    # radiant-polaris is multi-realm-capable (polaris.realm-context.realms=radiant); send the realm
    # explicitly, like the Radiant Iceberg init job does.
    "spark.sql.catalog.opendatalake.header.Polaris-Realm": POLARIS_REALM,
    "spark.sql.catalog.opendatalake.token-refresh-enabled": "false",
    "spark.sql.catalog.opendatalake.client.region": "us-east-1",
    # S3FileIO must talk to MinIO, not AWS. Set the endpoint + static creds explicitly rather than
    # relying on Polaris credential vending (vended endpoint wasn't applied -> S3FileIO fell back to
    # real AWS S3 and got 404 NoSuchBucket). Polaris here manages metadata only.
    "spark.sql.catalog.opendatalake.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
    "spark.sql.catalog.opendatalake.s3.endpoint": MINIO_ENDPOINT,
    "spark.sql.catalog.opendatalake.s3.path-style-access": "true",
    "spark.sql.catalog.opendatalake.s3.access-key-id": "admin",
    "spark.sql.catalog.opendatalake.s3.secret-access-key": "password",
    # dev.conf ships only inside the fat JAR as config/prd.conf; expose config/dev.conf here.
    "spark.driver.extraClassPath": _CONF_EXTRA_CLASSPATH,
}

# Lower than the standalone Open Datalake sandbox (1/4Gi req, 2/6Gi limit): here the pod competes
# with StarRocks CN (4Gi), StarRocks FE (1Gi), Polaris, Keycloak and the Airflow pods inside the
# same 12GB minikube. Raise via env if an import OOMKills (exit 137) on a larger source.
_CONTAINER_RESOURCES = k8s.V1ResourceRequirements(
    requests={
        "cpu": os.getenv("OPENDATALAKE_SPARK_CPU", "500m"),
        "memory": os.getenv("OPENDATALAKE_SPARK_MEMORY", "2Gi"),
    },
    limits={
        "cpu": os.getenv("OPENDATALAKE_SPARK_CPU_LIMIT", "2"),
        "memory": os.getenv("OPENDATALAKE_SPARK_MEMORY_LIMIT", "3Gi"),
    },
)

# Keep under the container memory limit above -- the JVM heap is only part of the pod's footprint.
DEFAULT_DRIVER_MEMORY = os.getenv("OPENDATALAKE_SPARK_DRIVER_MEMORY", "2g")


def _conf_flags(spark_conf: dict[str, str]) -> list[str]:
    flags: list[str] = []
    for key, value in spark_conf.items():
        flags += ["--conf", f"{key}={value}"]
    return flags


class EmrServerlessJobOperator(KubernetesPodOperator):
    def __init__(
        self,
        *,
        entry_point_arguments: list,
        entry_class: str = DEFAULT_ENTRY_CLASS,
        spark_conf: dict | None = None,
        name: str | None = None,  # EMR job name; unused (pod name derives from task_id)
        driver_memory: str = DEFAULT_DRIVER_MEMORY,
        **kwargs,
    ):
        # Drop EMR Serverless-only kwargs so they never reach KubernetesPodOperator.
        for emr_only in (
            "waiter_delay",
            "waiter_max_attempts",
            "wait_for_completion",
            "deferrable",
            "emr_config",
        ):
            kwargs.pop(emr_only, None)

        merged_conf = {**_LOCAL_SPARK_CONF, **(spark_conf or {})}
        # spark-submit options first, then the app JAR, then the ETL command/args (entry_point_arguments,
        # which may contain templated XComArgs -- `arguments` is a KubernetesPodOperator template field).
        arguments = [
            *_conf_flags(merged_conf),
            "--master",
            "local[*]",
            "--driver-memory",
            driver_memory,
            "--class",
            entry_class,
            JAR_PATH,
            *entry_point_arguments,
        ]

        super().__init__(
            namespace=NAMESPACE,
            image=SPARK_IMAGE,
            image_pull_policy="IfNotPresent",
            cmds=["/opt/spark/bin/spark-submit"],
            arguments=arguments,
            container_resources=_CONTAINER_RESOURCES,
            get_logs=True,
            is_delete_operator_pod=True,
            **kwargs,
        )
