# POC Airflow 3

Ce POC a pour objectif de préparer la migration vers Airflow 3 en validant la compatibilité des DAGs sur Airflow 2 et Airflow 3.

Pendant la période de transition, il sera nécessaire de supporter les deux versions:
- **CQDG** : on reste sur Airflow 2 pour le moment, car Airflow est partagé avec l'équipe CQDG
- **CHOP** : migration prévue vers Airflow 3

L’objectif est de s’assurer que les DAGs fonctionnent correctement sur les deux versions d’Airflow.  Ce POC se limite à ce qui est réaliste dans l’environnement sandbox. Il ne couvre pas la procédure de déploiement dans AWS (MWAA), ni les tests avec les composants spécifiques à AWS (comme l’ECS operator).

## Modifications

### Images docker et dépendances python
- Image docker airflow3: mise à jour de `requirements-airflow.txt` et du Dockerfile (voir folder docker-airflow3). Cette image est destinée uniquement au sandbox, avec l'objectif de se rapprocher de l'environnement AWS, même si elle ne sera pas parfaitement identique. L'image Airflow 2 doit continuer d'être produite et etre utilisée sur CQDG.
- Adaptation "best effort" pour la procédure de déploiement sur MWAA: modifications
suffisantes pour permettre de rouler la commande `docker build` (voir folder mwaa3).
- Image docker pour opérateurs ECS/Kubernetes: Aucun changement requis

### Helm chart

Pour pouvoir tester via le sandbox sur soi airflow2 ou airflow3:
- Copier l’ancien fichier values dans `airflow2-values.yaml`.
- Créer un nouveau `airflow3-values.yaml` dans ce sandbox.

À noter que cette modification s'appliquerait seulement au sandbox. Dans l'environnement CQDG, ce ne serait pas nécessaire de modifier le helm chart tant qu’on reste sur Airflow 2.

### Petits changements dans les dags

Les dags ne compilaient pas initialement sur Airflow 3. Les correctifs nécessaires sont disponibles dans la branche suivante:
https://github.com/radiant-network/radiant-portal-pipeline/tree/feat/SJRA-1419-make-dags-compatible-with-airflow3


## Procédure de test

Suivre le README. 

Pour installer Airflow 2, utiliser cette commande helm:
 helm install airflow apache-airflow/airflow  --version 1.19.0  -f values/airflow2-values.yaml 

Pour Airflow 3 :
	 - Construire l’image Docker :
		 ```
		 cd docker-airflow3
		 eval $(minikube -p minikube docker-env)
		 docker build -t ghcr.io/radiant-network/radiant-airflow3:1.0.5 .
		 ```
	 -  helm install airflow apache-airflow/airflow  --version 1.21.0  -f values/airflow3-values.yaml 

## Points à approfondir
- Tester dans AWS la procédure de déploiement (folder mwaa3) et l’ECS operator.

- Essayer la règle Ruff recommandée pour la migration Airflow 3:
  https://airflow.apache.org/docs/apache-airflow/stable/installation/upgrading_to_airflow3.html#step-3-dag-authors-check-your-airflow-dags-for-compatibility

- Run Diagnostics dag: cannot successfully execute first task on both versions

## Problèmes rencontrés
- Problème avec le udf 1.2.0 lors du deuxième DAG :
	```
	MySQLdb.ProgrammingError: (1064, 'org/radiant/VariantIdUDF has been compiled by a more recent version of the Java Runtime (class file version 61.0), this version of the Java Runtime only recognizes class file versions up to 55.0')
	```
  Solution: la version 1.1.0 a été utilisée dans ce POC.
- Helm chart : Les dernières versions ne supportent plus Airflow 2.10.5. Solution : préciser la version du chart (`1.19.0` pour Airflow 2, `1.21.0` pour Airflow 3).
- Après `helm repo update`, installation d’Airflow 2 impossible sans un user role : ajouté dans `airflow2-values.yaml`.
