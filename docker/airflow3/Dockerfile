FROM --platform=$BUILDPLATFORM apache/airflow:3.0.6-python3.12

USER airflow

RUN mkdir -p /home/airflow/.venv/radiant

RUN python3 -m venv /home/airflow/.venv/radiant


# POC note: À explorer — peut-on remplacer l’option --no-deps (qui évite d’installer les dépendances transitives)
# par l’utilisation d’un fichier de contraintes (--constraint) ?
COPY requirements-airflow.txt /home/airflow/.venv/radiant/requirements-airflow.txt
RUN /home/airflow/.venv/radiant/bin/pip install --no-deps -r /home/airflow/.venv/radiant/requirements-airflow.txt
