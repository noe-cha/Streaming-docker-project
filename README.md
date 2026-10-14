Projet de Streaming VOD
Ce dépôt contient l'infrastructure d'une plateforme de streaming VOD conçue en micro-services. Le projet tourne sous Docker Compose pour faciliter le déploiement, combinant une architecture de services interconnectés et l'intégration de Jellyfin adossé à un stockage objet S3 via Rclone.

Architecture globale
Voici la modélisation de l'architecture de la plateforme :

Extrait de code
flowchart TD
    User([Navigateur Web]) --> RP[Reverse Proxy Nginx]
    
    subgraph Docker Compose (Gestion via Arcane)
        
        subgraph Services Médias
            Jelly[Jellyfin :8096]
            Rclone[Rclone / FUSE]
        end

        subgraph Data & Stockage
            S3[(Garage S3 :3900)]
            DB[(PostgreSQL :5432)]
            Cache[(Redis :6379)]
        end

        subgraph Administration
            Arcane[Arcane :3552]
        end

        Jelly -->|lit les flux| Rclone
        Rclone -->|monte le bucket| S3
        Jelly -. stocke config .-> Home[(Hôte /home)]
    end
Stack Technique
Serveur Multimédia : Jellyfin (Port 8096) pour la gestion et la lecture de la bibliothèque VOD.

Pont de Stockage : Rclone assurant le montage FUSE du stockage objet S3 en tant que répertoire local (./media) avec gestion des collisions (--allow-non-empty).

Stockage Objet : Garage S3 (Port 3900) pour la conservation décentralisée des flux vidéos.

Base de données & Cache : PostgreSQL pour les métadonnées et Redis pour la gestion des données transitoires.

Administration : Arcane (Port 3552) pour le monitoring et la supervision locale des conteneurs.

    Procédure de Connexion Git et Déploiement
1. Configuration de Git sur la machine
Si tu récupères le projet sur une nouvelle machine (ou un nouveau conteneur Proxmox), configure d'abord ton identité Git :

Bash
git config --global user.name "Ton Nom"
git config --global user.email "ton.email@exemple.com"
2. Clonage ou Initialisation du Dépôt
Si le dépôt existe déjà sur GitHub/GitLab :

Bash
git clone <URL_DE_TON_DEPOT> /Streaming-docker-project
cd /Streaming-docker-project
Si tu pars d'un dossier local vide et que tu veux l'initialiser et le lier à un dépôt distant :

Bash
cd /Streaming-docker-project
git init
git remote add origin <URL_DE_TON_DEPOT>
git branch -M main
    Comment lancer le projet
Initialiser la configuration d'environnement :
Créer et configurer le fichier .env à la racine avec les identifiants requis :

Bash
cp .env.exemple .env
Lancer les services :

Bash
docker compose up -d
Accès aux interfaces :

Jellyfin (Lecteur & Administration VOD) : http://<IP_DEBIAN>:8096

Arcane (Dashboard de gestion) : http://<IP_DEBIAN>:3552

Garage S3 API : http://<IP_DEBIAN>:3900

Notes et problèmes rencontrés
Contraintes d'espace disque sur les partitions Debian :
L'hôte Debian présente une fragmentation des partitions avec un espace restreint sur /var, provoquant des erreurs de seuil critique (exigences de 2 Go par Jellyfin). Le problème a été résolu en déportant le volume de configuration de Jellyfin (./jellyfin-config) directement sur la partition /home (bénéficiant d'un espace de stockage confortable).

Gestion des points de montage FUSE avec Rclone :
Des conflits de verrouillage de dossiers déjà montés lors des redémarrages de conteneurs ont été neutralisés par l'intégration de l'argument --allow-non-empty dans la commande de montage Rclone.