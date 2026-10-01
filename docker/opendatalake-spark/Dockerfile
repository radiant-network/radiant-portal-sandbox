
FROM apache/spark:3.5.5

USER root
WORKDIR /opt/app

COPY target/scala-2.12/radiant-open-datalake-spark.jar /opt/app/radiant-open-datalake-spark.jar

COPY src/main/resources/config/prd.conf /opt/app/conf-extra/config/dev.conf
                                                     OPENDATALAKE_EMR_WAREHOUSE_S3
RUN sed -i \
    -e 's#s3a://opendatalake-prd/iceberg#s3://opendatalake-dev/iceberg#g' \
    -e 's#opendatalake-prd#opendatalake-dev#g' \
    /opt/app/conf-extra/config/dev.conf

RUN chown -R spark:spark /opt/app

USER spark
