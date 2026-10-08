#!/usr/bin/env bash
# Met à jour l'application Kendevis sur le serveur.
# Voir deploy/update.sh pour le mode d'emploi.

set -euo pipefail

CHEMIN_APP="${CHEMIN_APP:-/home/$(whoami)/kendevis}"
NOM_UTILISATEUR="${NOM_UTILISATEUR:-$(whoami)}"
NOM_BASE="${NOM_BASE:-kendevis}"
PYTHON="$CHEMIN_APP/venv/bin/python"
PIP="$CHEMIN_APP/venv/bin/pip"

cd "$CHEMIN_APP"

SAUVEGARDE="$CHEMIN_APP/sauvegardes/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$CHEMIN_APP/sauvegardes"

echo "==> Sauvegarde de la base de données"
if grep -q '^DB_ENGINE=django.db.backends.postgresql' .env 2>/dev/null; then
    # pg_dump avec les variables du .env, sans afficher le mot de passe.
    set -a; . ./.env; set +a
    PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" \
        | gzip > "$SAUVEGARDE.sql.gz"
else
    cp db.sqlite3 "$SAUVEGARDE.sqlite3"
fi
echo "    Sauvegarde : $SAUVEGARDE"

echo "==> Récupération de la nouvelle version"
git pull --ff-only

echo "==> Mise à jour des dépendances"
"$PIP" install --quiet -r requirements.txt

echo "==> Application des migrations"
"$PYTHON" manage.py migrate --noinput

echo "==> Collecte des fichiers statiques"
"$PYTHON" manage.py collectstatic --noinput

echo "==> Redémarrage du service"
sudo systemctl restart kendevis
sleep 2
sudo systemctl --no-pager status kendevis | head -n 12 || true

echo "==> Nettoyage des sauvegardes de plus de 30 jours"
find "$CHEMIN_APP/sauvegardes" -type f -mtime +30 -delete

echo
echo "✔ Mise à jour terminée."
echo "  Sauvegarde conservée : $SAUVEGARDE"