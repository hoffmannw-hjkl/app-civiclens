#!/bin/bash
# ==============================================================================
# Déploiement automatisé de CivicLens sur le GCP AI Foundation Blueprint
# ==============================================================================
set -e

BLUEPRINT_DIR=""
TAG="latest"

for arg in "$@"; do
    case $arg in
        --blueprint-dir=*)
            BLUEPRINT_DIR="${arg#*=}"
            shift
            ;;
        --tag=*)
            TAG="${arg#*=}"
            shift
            ;;
    esac
done

if [ -z "$BLUEPRINT_DIR" ]; then
    if [ -d "../gcp-ai-foundation-blueprint" ]; then
        BLUEPRINT_DIR="../gcp-ai-foundation-blueprint"
    elif [ -d "/usr/local/google/home/hoffmannw/gcp-ai-foundation-blueprint" ]; then
        BLUEPRINT_DIR="/usr/local/google/home/hoffmannw/gcp-ai-foundation-blueprint"
    else
        echo "❌ Erreur: Impossible de localiser le répertoire du blueprint. Spécifiez --blueprint-dir=/chemin/vers/gcp-ai-foundation-blueprint"
        exit 1
    fi
fi

echo "========================================================================"
echo "🚀 Déploiement de CivicLens sur le Blueprint : ${BLUEPRINT_DIR}"
echo "========================================================================"

# 1. Extraction des outputs Terraform du Blueprint
echo "📋 1. Lecture des configurations Terraform du Blueprint..."
PROJECT_ID=$(terraform -chdir="${BLUEPRINT_DIR}" output -raw project_id 2>/dev/null || gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Erreur: gcloud project non défini."
    exit 1
fi

GKE_CLUSTER=$(terraform -chdir="${BLUEPRINT_DIR}" output -raw gke_cluster_name 2>/dev/null || echo "ai-demo-2e2m-gke")
GKE_REGION=$(terraform -chdir="${BLUEPRINT_DIR}" output -raw region 2>/dev/null || terraform -chdir="${BLUEPRINT_DIR}" output -raw gke_region 2>/dev/null || echo "europe-west1")
GKE_SA=$(terraform -chdir="${BLUEPRINT_DIR}" output -raw gke_app_service_account_email 2>/dev/null || terraform -chdir="${BLUEPRINT_DIR}" output -raw gke_ai_service_account 2>/dev/null || echo "ai-demo-2e2m-gke-ai-sa@${PROJECT_ID}.iam.gserviceaccount.com")
BASTION_NAME=$(terraform -chdir="${BLUEPRINT_DIR}" output -raw bastion_name 2>/dev/null || echo "ai-demo-2e2m-bastion")
BASTION_ZONE=$(terraform -chdir="${BLUEPRINT_DIR}" output -raw bastion_zone 2>/dev/null || echo "europe-west1-b")

AR_REPO="ai-demo-repo"
IMAGE_URI="${GKE_REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/civiclens-api:${TAG}"

echo "   • Projet GCP     : ${PROJECT_ID}"
echo "   • Cluster GKE    : ${GKE_CLUSTER} (${GKE_REGION})"
echo "   • Workload ID SA : ${GKE_SA}"
echo "   • Image Cible    : ${IMAGE_URI}"
echo "   • Bastion IAP    : ${BASTION_NAME} (${BASTION_ZONE})"

# 2. Construction et publication de l'image conteneur
echo "🔨 2. Construction de l'image Docker multi-arch / linux-amd64..."
gcloud builds submit src/ \
    --tag="${IMAGE_URI}" \
    --project="${PROJECT_ID}"

# 3. Préparation des manifests avec les valeurs réelles
echo "📝 3. Génération des manifests Kubernetes..."
MANIFEST_DIR="/tmp/civiclens-deploy"
rm -rf "$MANIFEST_DIR"
mkdir -p "$MANIFEST_DIR"
cp deploy/k8s/*.yaml "$MANIFEST_DIR/"

sed -i -E "s|image: .*/civiclens-api:.*|image: ${IMAGE_URI}|g" "$MANIFEST_DIR/deployment.yaml"
sed -i -E "s|iam\.gke\.io/gcp-service-account:.*|iam.gke.io/gcp-service-account: \"${GKE_SA}\"|g" "$MANIFEST_DIR/service-account.yaml"
sed -i "s|wh-djvagl|${PROJECT_ID}|g" "$MANIFEST_DIR/deployment.yaml"
if [ -n "${DB_HOST:-}" ]; then
    sed -i "s|value: \"10.238.0.2\"|value: \"${DB_HOST}\"|g" "$MANIFEST_DIR/deployment.yaml"
fi

# 4. Déploiement via le tunnel Bastion IAP
echo "🚀 4. Application des manifests sur GKE Autopilot via Bastion IAP..."
gcloud compute scp "$MANIFEST_DIR"/* "${BASTION_NAME}:/tmp/" \
    --zone="${BASTION_ZONE}" \
    --tunnel-through-iap \
    --project="${PROJECT_ID}"

gcloud compute ssh "${BASTION_NAME}" \
    --zone="${BASTION_ZONE}" \
    --tunnel-through-iap \
    --project="${PROJECT_ID}" \
    --command="
        set -e
        export HTTPS_PROXY='http://localhost:8888'
        gcloud container clusters get-credentials ${GKE_CLUSTER} --region=${GKE_REGION} --project=${PROJECT_ID}
        kubectl apply -f /tmp/namespace.yaml
        kubectl apply -f /tmp/service-account.yaml
        kubectl apply -f /tmp/backend-config.yaml
        kubectl apply -f /tmp/deployment.yaml
        kubectl apply -f /tmp/service.yaml
        kubectl apply -f /tmp/ingress.yaml 2>/dev/null || true
        echo 'Pods en cours d'exécution :'
        kubectl get pods -n civiclens -o wide
    "

rm -rf "$MANIFEST_DIR"
echo "========================================================================"
echo "✅ Déploiement terminé avec succès !"
echo "========================================================================"
