# Gene panels (RAD-10)

Mock input for the `radiant-import-tenant-gene-panel` DAG (radiant-portal-pipeline), which sends the file to
the portal `PUT /{tenant}/gene_panels`. One file per tenant, under `<tenant>/gene_panels.tsv`. The file is the
full list of the tenant's panels: each upload replaces the previous one.

## Format

UTF-8 TSV, one gene per row, with a header row:

```
symbol	panels	version
KCNQ1	CARDIAC_ARRHYTHMIA,HEREDITARY_CANCER	CARDIAC_ARRHYTHMIA_v1,HEREDITARY_CANCER_v1
```

- **`symbol`:** the gene symbol, one per row.
- **`panels`:** the comma-separated codes of the panels the gene is in. A code the tenant already has (any case)
  gets the genes of the file and keeps its name; a new code creates a panel named by its code.
- **`version`:** ignored by the portal (optional).

## `radiant/gene_panels.tsv`

6 panels, 35 gene rows. Every gene is a protein-coding chr11 gene with variants in all the sandbox SNV VCFs
(germline SH032, CEPH-1463; somatic SRX1091647-T, SRX1166091-T), so each panel has hits in the facet.

| Panel | Genes |
|---|---|
| CARDIAC_ARRHYTHMIA | 6 |
| CARDIOMYOPATHY | 4 |
| HEMOGLOBINOPATHY | 5 |
| RETINAL_DYSTROPHY | 7 |
| HEREDITARY_CANCER | 10 |
| MONOGENIC_DIABETES | 4 |

Rows that test the edge cases:

| Line | Row | Purpose |
|---|---|---|
| 2 | `KCNQ1` (CARDIAC_ARRHYTHMIA, HEREDITARY_CANCER) | one gene in two panels (both 11p15 / Beckwith-Wiedemann region) |
| 32 | `NOTAGENE1` (HEREDITARY_CANCER) | symbol matches no Ensembl gene: the row is skipped with a warning, or rejected with `strict` |
| 36 | `GHOST1` (MONOGENIC_DIABETES) | symbol matches no Ensembl gene: same as line 32 |

Expected answers:

| `strict` | Result |
|---|---|
| `false` | 200, `{"panels": 6, "genes": 34, "warnings": [2 rows]}` |
| `true` | 422, nothing changed, the two unmatched rows (lines 32, 36) in `detail.warnings` |

The facet shows the panel codes as names (`CARDIAC_ARRHYTHMIA`, …): the sandbox has no analysis catalog panel with
these codes.

## Run it

```bash
aws s3 cp data/gene_panels/radiant/gene_panels.tsv s3://warehouse/gene_panels/radiant/gene_panels.tsv
```

The DAG uses the Airflow connection `radiant_api_conn`. The sandbox sets it as `AIRFLOW_CONN_RADIANT_API_CONN`
in `values/airflow3-values.yaml`: the `radiant-cli` Keycloak client against `http://radiant-api:8090`.

The `radiant-cli` service-account user also needs tenant access and the `can_manage_analysis_catalog` action in
the portal. `k8s/api/radiant-cli-grant-job.yml` (applied with `kubectl apply -f k8s/api/`) grants it `tenant_admin` (and
`data_manager` at `*`, for case registration) in tenant `radiant` once the API has run its migrations. Without it the DAG fails with 403.

Trigger with:

```json
{"tenant": "radiant", "gene_panel_filepath": "s3://warehouse/gene_panels/radiant/gene_panels.tsv", "strict": false}
```
