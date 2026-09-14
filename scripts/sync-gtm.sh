#!/bin/bash
# ==============================================================================
# Synchronisation Git & Pull Requests vers cloud-gtm/app-civiclens
# ==============================================================================
set -e

FORCE=false
THRESHOLD=5

for arg in "$@"; do
    case $arg in
        --force|-f)
            FORCE=true
            shift
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_DIR"

echo "🔍 Vérification de l'état de synchronisation avec cloud-gtm/app-civiclens..."

if ! git remote | grep -q "^gtm$"; then
    git remote add gtm https://github.com/cloud-gtm/app-civiclens.git
fi

git fetch gtm main --quiet 2>/dev/null || true

COMMITS_AHEAD=$(git rev-list --count gtm/main..HEAD 2>/dev/null || echo 0)
echo "📊 Commits locaux en attente de synchronisation vers GTM : ${COMMITS_AHEAD} (seuil : ${THRESHOLD})"

if [ "$COMMITS_AHEAD" -lt "$THRESHOLD" ] && [ "$FORCE" = false ]; then
    echo "ℹ️ Seuil non atteint. Synchronisation différée (utilisez --force pour forcer)."
    exit 0
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SYNC_BRANCH="sync/batch-${TIMESTAMP}"
LAST_COMMIT_MSG=$(git log -1 --pretty=%B | head -n 1)

echo "🚀 Préparation de la synchronisation vers cloud-gtm/app-civiclens..."
echo "   Branche temporaire : ${SYNC_BRANCH}"
echo "   Titre de la PR      : ${LAST_COMMIT_MSG}"

git checkout -b "${SYNC_BRANCH}" --quiet

echo "📤 Push de la branche vers cloud-gtm/app-civiclens..."
git push gtm "${SYNC_BRANCH}" --quiet

echo "📝 Création de la Pull Request..."
PR_BODY=$(git log gtm/main..HEAD --oneline | sed 's/^/- /')
PR_URL=$(gh pr create \
    --repo cloud-gtm/app-civiclens \
    --title "${LAST_COMMIT_MSG}" \
    --body "### Commits inclus dans ce lot de synchronisation :

${PR_BODY}

---
*Synchronisé automatiquement via sync-gtm.sh*" \
    --head "${SYNC_BRANCH}" \
    --base main)

echo "🔗 PR créée : ${PR_URL}"

echo "⚡ Auto-fusion (merge) de la PR..."
gh pr merge "${PR_URL}" --merge --delete-branch

echo "🔄 Synchronisation locale et mise à jour de github/main..."
git checkout main --quiet
git branch -D "${SYNC_BRANCH}" --quiet
git pull gtm main --quiet
git push origin main --quiet

echo "🎉 Synchronisation réussie ! ${COMMITS_AHEAD} commit(s) intégrés à cloud-gtm/app-civiclens/main."
