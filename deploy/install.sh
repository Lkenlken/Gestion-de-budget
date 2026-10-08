# Déploiement sur un serveur Linux (Oracle Cloud Always Free)
#
# Tout ce script s'exécute SUR LE SERVEUR, en root ou avec sudo.
# Il installe : Python, PostgreSQL, gunicorn, nginx et HTTPS (Let's Encrypt).
#
#   sudo bash deploy/install.sh
#
# Variables à Adapter avant exécution :
#   DOMAINE      nom de domaine ou IP publique du serveur
#   NOM_UTILISATEUR  utilisateur Linux propriétaire des fichiers (ex: ubuntu)
#   CHEMIN_APP   dossier de l'application
#   EMAIL_CERTBOT e-mail pour les renouvellement du certificat

set -euo pipefail

DOMAINE="${DOMAINE:?Définissez DOMAINE (ex : budget.mondomaine.com ou l'IP)}"
NOM_UTILISATEUR="${NOM_UTILISATEUR:-ubuntu}"
CHEMIN_APP="${CHEMIN_APP:-/home/$NOM_UTILISATEUR/kendevis}"
EMAIL_CERTBOT="${EMAIL_CERTBOT:-admin@mondomaine.com}"
NOM_BASE="${NOM_BASE:-kendevis}"

echo "==> 1/8 Mise à jour du système"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

echo "==> 2/8 Installation de Python, PostgreSQL, nginx et les outils"
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib \
    nginx \
    git curl ca-certificates \
    libpq-dev build-essential

echo "==> 3/8 Création de la base de données PostgreSQL"
# Mot de passe généré ici, écrit dans un fichier lisible par root uniquement.
MOT_DE_PASSE_BD="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE USER $NOM_BASE WITH PASSWORD '$MOT_DE_PASSE_BD';
CREATE DATABASE $NOM_BASE OWNER $NOM_BASE;
SQL

# On communicates le mot de passe au fichier .env (sans l'y conserver en clair
# dans le dépôt) : il ne reste que sur le serveur.
if [ -f $CHEMIN_APP/.env ]; then
    sed -i "/^DB_PASSWORD=/d" $CHEMIN_APP/.env
    printf 'DB_PASSWORD=%s\n' "$MOT_DE_PASSE_BD" >> $CHEMIN_APP/.env
    chown $NOM_UTILISATEUR:$NOM_UTILISATEUR $CHEMIN_APP/.env
    chmod 600 $CHEMIN_APP/.env
fi
unset MOT_DE_PASSE_BD
echo "    Utilisateur PostgreSQL '$NOM_BASE' créé, mot de passe placé dans .env"

echo "==> 4/8 Environnement Python et installation des dépendances"
sudo -u $NOM_UTILISATEUR -H bash -c "
    python3 -m venv $CHEMIN_APP/venv
    $CHEMIN_APP/venv/bin/pip install --quiet --upgrade pip
    $CHEMIN_APP/venv/bin/pip install --quiet -r $CHEMIN_APP/requirements.txt
"

echo "==> 5/8 Collecte des fichiers statiques et migrations"
sudo -u $NOM_UTILISATEUR -H bash -c "
    cd $CHEMIN_APP
    $CHEMIN_APP/venv/bin/python manage.py collectstatic --noinput
    $CHEMIN_APP/venv/bin/python manage.py migrate --noinput
"

echo "==> 6/8 Service applicatif (gunicorn)"
cat > /etc/systemd/system/kendevis.service <<SERVICE
[Unit]
Description=Kendevis - gestion de budget
After=network.target postgresql.service

[Service]
User=$NOM_UTILISATEUR
Group=$NOM_UTILISATEUR
WorkingDirectory=$CHEMIN_APP
EnvironmentFile=$CHEMIN_APP/.env
ExecStart=$CHEMIN_APP/venv/bin/gunicorn \\
    --workers 3 \\
    --timeout 60 \\
    --bind unix:/run/kendevis.sock \\
    gestion_budget.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

echo "==> 7/8 Configuration de nginx et certificat HTTPS"
cat > /etc/nginx/sites-available/kendevis <<NGINX
server {
    listen 80;
    server_name $DOMAINE;

    # Taille maximale d'un envoi de fichier
    client_max_body_size 12m;

    # Les fichiers statiques sont servis par WhiteNoise (dans Django) :
    # ce bloc ne sert que de secours et peut être supprimé.
    location /static/ {
        alias $CHEMIN_APP/staticfiles/;
        expires 30d;
        access_log off;
    }

    location / {
        proxy_pass http://unix:/run/kendevis.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        # Indispensable : Django doit savoir que la requête est en HTTPS.
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/kendevis /etc/nginx/sites-enabled/kendevis
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable --now kendevis
nginx -t && systemctl reload nginx

echo "==> 8/8 Certificat HTTPS gratuit (Let's Encrypt)"
apt-get install -y -qq certbot python3-certbot-nginx
if ip addr show 2>/dev/null | grep -q "inet $DOMAINE"; then
    echo "    Certificat RSA indisponible pour une IP brute (Let's Encrypt ne"
    echo "    délivre pas de certificat pour une adresse IP). Passage en HTTP."
else
    certbot --nginx \
        --non-interactive \
        --agree-tos \
        --email $EMAIL_CERTBOT \
        --redirect \
        -d $DOMAINE || {
            echo "⚠ Certificat impossible (nom de domaine non encore résolu ?)."
            echo "  L'application fonctionne en HTTP : $DOMAINE"
            exit 0
        }
fi

echo
echo "============================================================"
echo "✔ Installation terminée."
echo
echo "  Application : http://$DOMAINE"
echo "  Administration : http://$DOMAINE/admin/"
echo
echo "Étapes restantes :"
echo "  1. Renseigner SECRET_KEY / DB_PASSWORD dans $CHEMIN_APP/.env"
echo "  2. sudo systemctl restart kendevis"
echo "  3. Créer le compte administrateur :"
echo "       cd $CHEMIN_APP && sudo -u $NOM_UTILISATEUR -H ./venv/bin/python manage.py creer_admin"
echo "============================================================"