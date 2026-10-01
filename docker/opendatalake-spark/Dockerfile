# Sandbox image for the Open Datalake Spark ETL: bundles the fat JAR on top of Apache Spark 3.5.5
# so the Airflow KubernetesPodOperator can run `spark-submit --master local[*]` inside minikube,
# in place of EMR Serverless.
#
# The build context is the `spark/` directory of the sibling radiant-open-datalake checkout (COPY
# paths below are relative to it), not this repo. Build the JAR first, then the image:
#
#   cd ../radiant-open-datalake/spark && sbt clean assembly
#   cd ../../radiant-portal-sandbox
#   eval $(minikube -p minikube docker-env)
#   docker build -t ghcr.io/radiant-network/opendatalake-spark:latest \
#     -f docker/opendatalake-spark/Dockerfile ../radiant-open-datalake/spark
FROM apache/spark:3.5.5

USER root
WORKDIR /opt/app

# Fat JAR produced by `sbt clean assembly`. spark-sql / hadoop-client are Provided and supplied by
# the base image; hadoop-aws, iceberg and glow are shaded in, so no --packages at runtime.
COPY target/scala-2.12/radiant-open-datalake-spark.jar /opt/app/radiant-open-datalake-spark.jar

# The import DAG loads its dataset config from the classpath as `config/<environment>.conf`
# (OPENDATALAKE_ENVIRONMENT defaults to "dev" in the sandbox). Only prd.conf ships in the JAR, so
# expose a dev.conf on an extra classpath dir.
COPY src/main/resources/config/prd.conf /opt/app/conf-extra/config/dev.conf

# Point storage at the sandbox RustFS bucket (opendatalake-dev). FerLab uses the iceberg StorageConf
# path as the Iceberg table LOCATION, so the baked prd bucket must be rewritten or writes 404 with
# NoSuchBucket. Use the s3:// scheme for iceberg (Iceberg S3FileIO + the Polaris allowedLocations set
# by radiant-polaris-init-opendatalake-catalog-job expect it); raw stays s3a:// for Hadoop (and is
# overridden at runtime via --raw-storage anyway).
#
# SHARED CONSTANT -- bucket `opendatalake-dev` / root `s3://opendatalake-dev/iceberg` is hardcoded
# in four places that must agree. A mismatch surfaces as a 404 NoSuchBucket at Iceberg write time,
# not as a config error:
#   k8s/rustfs/radiant-rustfs-bucket-init-job.yaml       creates the bucket
#   k8s/polaris/init/radiant-polaris-init-opendatalake-catalog-job.yaml
#                                                      CATALOG_WAREHOUSE / allowedLocations
#   docker/opendatalake-spark/Dockerfile               <- here, sed rewrite of the baked config
#   values/airflow3-values.yaml                        OPENDATALAKE_RAW_BUCKET,
#                                                      OPENDATALAKE_EMR_WAREHOUSE_S3
RUN sed -i \
    -e 's#s3a://opendatalake-prd/iceberg#s3://opendatalake-dev/iceberg#g' \
    -e 's#opendatalake-prd#opendatalake-dev#g' \
    /opt/app/conf-extra/config/dev.conf

RUN chown -R spark:spark /opt/app

USER spark
