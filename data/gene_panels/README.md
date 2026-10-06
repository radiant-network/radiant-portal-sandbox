# Gene panels (RAD-10)

Mock input for the `radiant-import-tenant-gene-panel` DAG (radiant-portal-pipeline), which sends the file to
the portal `PUT /{tenant}/gene_panels`. One file per tenant, under `<tenant>/gene_panels.tsv`. The file is the
full list of the tenant's panels: each upload replaces the previous one.

## Format

UTF-8 TSV, one gene per row, one panel per column:

```
symbol	Cardiac arrhythmia	Cardiomyopathy	...
KCNQ1	true	false	...
```

- **First column:** the gene symbol, one per row. There is no Ensembl ID column.
- **Header of each following column:** the panel name. The portal derives the panel code from the name.
- **Cells:** `true` if the gene is in the panel, `false` if it is not. An empty cell is the same as `false`.

## `radiant/gene_panels.tsv`

6 panels, 35 gene rows. Every gene is a protein-coding chr11 gene with variants in all the sandbox SNV VCFs
(germline SH032, CEPH-1463; somatic SRX1091647-T, SRX1166091-T), so each panel has hits in the facet.

| Panel | Genes |
|---|---|
| Cardiac arrhythmia | 6 |
| Cardiomyopathy | 4 |
| Hemoglobinopathy | 5 |
| Retinal dystrophy | 7 |
| Hereditary cancer | 9 |
| Monogenic diabetes | 4 |

Rows that test the edge cases:

| Line | Row | Purpose |
|---|---|---|
| 32 | `NOTAGENE1` (Hereditary cancer) | symbol matches no Ensembl gene: the row is skipped with a warning, or rejected with `strict` |
| 36 | `GHOST1` (Monogenic diabetes) | symbol matches no Ensembl gene: same as line 32 |

Half of the non-member cells are `false` and half are empty (every second one, in file order), so both spellings
of "not in the panel" are tested in every panel column.

Expected answers:

| `strict` | Result |
|---|---|
| `false` | 200, `{"panels": 6, "genes": 33, "warnings": [2 rows]}` |
| `true` | 422, nothing changed, the two unmatched rows (lines 32, 36) in `detail.warnings` |

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
