FROM --platform=$BUILDPLATFORM apache/airflow:3.2.1-python3.12

USER airflow

RUN mkdir -p /home/airflow/.venv/radiant

RUN python3 -m venv /home/airflow/.venv/radiant

COPY requirements-airflow.txt /home/airflow/.venv/radiant/requirements-airflow.txt

# The constraints file is a copy from the official airflow constraint file for our airflow version (3.2.1)
# It acts as a build-time safeguard: pip will fail if any pin in requirements-airflow.txt drifts
COPY constraints-python3.12.txt /home/airflow/.venv/radiant/constraints-python3.12.txt
RUN /home/airflow/.venv/radiant/bin/pip install \
    --no-deps \
    --constraint /home/airflow/.venv/radiant/constraints-python3.12.txt \
    -r /home/airflow/.venv/radiant/requirements-airflow.txt

# Note: the Open Datalake DAGs import airflow.providers.amazon (S3Hook,
# EmrServerlessStartJobOperator) at parse time. No install is needed -- the base image already
# bundles apache-airflow-providers-amazon 9.25.0, the exact version constraints-python3.12.txt
# pins. Verify after a base-image bump with:
#   docker run --rm --user airflow --entrypoint python apache/airflow:3.2.1-python3.12 \
#     -c "import importlib.metadata as m; print(m.version('apache-airflow-providers-amazon'))"
