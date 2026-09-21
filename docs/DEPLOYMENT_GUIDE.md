# Guide de Déploiement : CivicLens sur GCP AI Foundation Blueprint 🚀

Ce document explique comment déployer l'application **CivicLens** sur une infrastructure provisionnée avec le **[GCP AI Foundation Blueprint](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint)**.

---

## 🏗️ Architecture du Déploiement Applicatif

```
                     ┌──────────────────────────────────────────────┐
                     │          Utilisateur / Navigateur            │
                     └──────────────────────┬───────────────────────┘
                                            │ HTTPS (443)
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │     Google Cloud External Load Balancer      │
                     │  - Cloud Armor WAF Policy (OWASP Top 10)     │
                     │  - Identity-Aware Proxy (IAP Zero Trust)     │
                     └──────────────────────┬───────────────────────┘
                                            │ NEG / ClusterIP
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Cluster GKE Autopilot Privé (Fourni par le Blueprint)                                  │
│                                                                                        │
│   Namespace: civiclens                                                                 │
│   ┌────────────────────────────────────────────────────────────────────────────────┐   │
│   │ Pod: civiclens-api (FastAPI + SPA Web / Python 3.11)                           │   │
│   │                                                                                │   │
│   │ Workload Identity KSA (civiclens-ksa) ──► GSA (${prefix}-gke-ai-sa)            │   │
│   └───────────────────────┬───────────────────────────────┬────────────────────────┘   │
└───────────────────────────┼───────────────────────────────┼────────────────────────────┘
                            │                               │
                            ▼                               ▼
            ┌──────────────────────────────┐ ┌──────────────────────────────┐
            │   Vertex AI Gemini & RAG     │ │   BigQuery AI Lakehouse      │
            │ - Gemini 2.5 Flash / Pro     │ │ - Balances communes 2000-2025│
            │ - text-embedding-005         │ │ - Ratios financiers M57      │
            └──────────────────────────────┘ └──────────────────────────────┘
```

---

## 📋 Prérequis

1. **Infrastructure de Base** : Avoir déployé le [GCP AI Foundation Blueprint](https://github.com/cloud-gtm/gcp-ai-foundation-blueprint) dans votre projet Google Cloud (cluster GKE Autopilot, VPC privé, Cloud Armor WAF, IAP).
2. **Base de Données & Stockage Analytique** :
   - **BigQuery Lakehouse** : Provisionné automatiquement par le Blueprint (`lakehouse_dataset_id`) pour les balances comptables OFGL et le Text-to-SQL.
   - **Cloud SQL PostgreSQL (`pgvector`)** : Utilisé pour la recherche sémantique vectorielle sur les actes administratifs. Si une instance Cloud SQL n'est pas encore connectée au VPC (`DB_HOST`), l'API démarre avec un repli gracieux et s'appuie sur le Lakehouse BigQuery et les APIs de Bercy.
3. **Outils installés localement** :
   - `gcloud` CLI (authentifié avec votre compte Google).
   - `kubectl` et `terraform` (v1.5+).
   - Droits `roles/container.developer` et `roles/iap.tunnelResourceAccessor`.

---

## ⚡ Méthode 1 : Déploiement Automatisé en 1 Commande (Recommandé)

Le script `./scripts/deploy-to-blueprint.sh` détecte automatiquement les paramètres générés par Terraform et orchestre le build et le déploiement sur GKE Autopilot :

```bash
# Se placer dans le répertoire de l'application
cd app-civiclens

# Lancer le déploiement en pointant vers le dossier du blueprint
./scripts/deploy-to-blueprint.sh --blueprint-dir=../gcp-ai-foundation-blueprint
```

### Ce que fait ce script :
1. Extrait les sorties Terraform (`project_id`, `region`, `gke_cluster_name`, `gke_app_service_account_email`, `bastion_name`, `bastion_zone`).
2. Construit l'image Docker multi-plateforme via Google Cloud Build et la pousse vers Artifact Registry.
3. Injecte les variables d'environnement dans les manifests Kubernetes (`deploy/k8s/`).
4. Se connecte au cluster GKE privé via le tunnel sécurisé IAP du bastion.
5. Applique les manifests (`kubectl apply`) et affiche l'état des Pods.

---

## 🛠️ Méthode 2 : Déploiement Manuel Étape par Étape

### 1. Build et Push de l'Image Conteneur
```bash
PROJECT_ID=$(gcloud config get-value project)
REGION="europe-west1"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-demo-repo/civiclens-api:latest"

gcloud builds submit src/ --tag="${IMAGE_URI}"
```

### 2. Adaptation des Manifests Kubernetes
Dans `deploy/k8s/deployment.yaml`, mettez à jour le champ `image:` avec votre URI de conteneur :
```yaml
containers:
  - name: api
    image: europe-west1-docker.pkg.dev/<VOTRE_PROJECT_ID>/ai-demo-repo/civiclens-api:latest
```

Dans `deploy/k8s/service-account.yaml`, liez le compte de service Kubernetes au GSA du Blueprint :
```yaml
annotations:
  iam.gke.io/gcp-service-account: ai-demo-2e2m-gke-ai-sa@<VOTRE_PROJECT_ID>.iam.gserviceaccount.com
```

### 3. Application sur le Cluster GKE (via le Bastion IAP)
Puisque le cluster GKE Autopilot est 100% privé, l'accès s'effectue via le Bastion :

```bash
# Transférer les manifests vers le bastion
gcloud compute scp deploy/k8s/*.yaml ai-demo-2e2m-bastion:/tmp/ \
    --zone=europe-west1-b --tunnel-through-iap

# Exécuter le déploiement sur le cluster
gcloud compute ssh ai-demo-2e2m-bastion --zone=europe-west1-b --tunnel-through-iap \
    --command="
      export HTTPS_PROXY='http://localhost:8888'
      gcloud container clusters get-credentials ai-demo-2e2m-gke --region=europe-west1
      kubectl apply -f /tmp/
      kubectl get pods -n civiclens
    "
```

---

## 🔍 Validation & Tests

1. **Vérifier l'état des Pods :**
   ```bash
   kubectl get pods -n civiclens
   ```
   *Tous les pods doivent être en état `Running` et `READY 1/1`.*

2. **Vérifier les sondes de santé (Healthcheck) :**
   ```bash
   kubectl logs -n civiclens -l app=civiclens-api --tail=50
   ```

3. **Accéder à l'application :**
   Ouvrez l'URL publique de votre Load Balancer HTTPS (`https://<VOTRE_IP_OU_DOMAINE>/`) et authentifiez-vous via Google Cloud Identity-Aware Proxy (IAP).
