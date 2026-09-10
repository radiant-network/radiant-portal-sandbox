"""Sandbox-only drop-in replacement for the Open Datalake ECS download operator.

radiant-portal-sandbox variant of `radiant-open-datalake/airflow/sandbox/operators/k8s.py`: the only
change is the namespace, which is the Radiant stack's (`radiant`) in the unified sandbox rather than
`opendatalake`.

UPSTREAM CONTRACT -- this file is a fork and nothing here is imported or linted by this repo, so
drift only shows up as a DAG-parse error in the sandbox. It depends on, and must be re-checked
against, `radiant-open-datalake/airflow/`:

    opendatalake.lib.config.s3_conn_id                  imported below
    opendatalake.dags.download_source                   constructs PythonScriptOperator with
                                                        script_name / script_args (+ ECS-only
                                                        secret_env_vars / secret_arn_env_vars)
    sandbox/operators/k8s.py                            the file this mirrors

The durable fix is to push the env-var parameterisation upstream and delete this copy; until then,
re-diff the two files whenever the Open Datalake operators change.

Install into the radiant-open-datalake checkout with:

    cp opendatalake/operators/k8s.py \
       ../radiant-open-datalake/airflow/opendatalake/lib/operators/k8s.py
    sed -i '' 's/operators\\.ecs/operators\\.k8s/g' \
       ../radiant-open-datalake/airflow/opendatalake/dags/download_source.py

Do NOT commit the swap into radiant-open-datalake: this operator has no place in the AWS deployment.
"""

import os

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

from opendatalake.lib import config

NAMESPACE = os.getenv("OPENDATALAKE_TASK_OPERATOR_KUBERNETES_NAMESPACE", "radiant")
TASK_OPERATOR_IMAGE = os.getenv(
    "OPENDATALAKE_TASK_OPERATOR_IMAGE", "ghcr.io/radiant-network/opendatalake-airflow-task-operator:latest"
)


def _get_k8s_context(extra_env_vars=None):
    # Note: passing the s3 connection variable as env vars for now.
    # There might be a better way to pass the connection info to the container.
    s3_conn_variable_prefix = "AIRFLOW_CONN_" + config.s3_conn_id.upper()
    env_vars = {k: v for k, v in os.environ.items() if k.startswith(s3_conn_variable_prefix)}
    env_vars.update(extra_env_vars or {})

    return dict(
        namespace=NAMESPACE,
        image=TASK_OPERATOR_IMAGE,
        image_pull_policy="IfNotPresent",
        get_logs=True,
        is_delete_operator_pod=True,
        env_vars=env_vars,
    )


class PythonScriptOperator(KubernetesPodOperator):
    def __init__(self, script_name, script_args, **kwargs):
        assert "cmds" not in kwargs, "Don't pass cmds: generated dynamically."

        # ECS-only kwargs (secrets forwarded via Secrets Manager ARN -> ECS task def env). The sandbox
        # pod gets its secrets from cluster-wide env vars (airflow3-values.yaml extraEnv), so drop them
        # here rather than forwarding to KubernetesPodOperator.
        for ecs_only in ("secret_env_vars", "secret_arn_env_vars"):
            kwargs.pop(ecs_only, None)

        super().__init__(**_get_k8s_context(), **kwargs)
        self.template_fields = self.template_fields + ("script_args", "script_name")

        self.script_name = script_name
        self.script_args = script_args

    def execute(self, context, **kwargs):
        self.cmds = ["python", self.script_name]
        for k, v in self.script_args.items():
            self.cmds.append(f"--{k}")
            self.cmds.append(str(v))
        return super().execute(context, **kwargs)
