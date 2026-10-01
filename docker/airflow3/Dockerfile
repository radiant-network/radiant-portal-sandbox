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
