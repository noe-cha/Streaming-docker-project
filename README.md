Projet de Streaming VOD

Ce dépôt contient l'infrastructure d'une plateforme de streaming VOD conçue en micro-services. Le projet tourne actuellement sous Docker Compose pour faciliter le développement en local, mais l'architecture a été pensée pour être déployable sur un cluster Kubernetes (K8s) à terme.

Architecture globale

Voici la modélisation de l'architecture actuelle et cible :

flowchart TD
    User([Navigateur Web]) --> RP[Reverse Proxy Nginx]
    
    subgraph Docker Compose (Gestion via Arcane)
        
        subgraph Frontend & Streaming
            RP --> Front[Frontend Nginx :3000]
            RP --> Stream[Streaming Nginx :8080]
            RP --> Jelly[Jellyfin - a venir]
        end

        subgraph Data & Stockage
            S3[(Garage S3 :3900)]
            DB[(PostgreSQL)]
            Cache[(Redis)]
        end

        subgraph Traitement
            Worker[Worker Python/FFmpeg]
        end

        Front -.-> Stream
        Stream -. lit le flux HLS .-> S3
        Worker -. ecrit les segments .-> S3
        Cache -. file d'attente .-> Worker
        Worker -. met a jour .-> DB
    end


Stack Technique

Frontend : Nginx (Alpine) servant une page HTML/JS simple avec hls.js.

Streaming : Nginx configuré en reverse proxy pour distribuer les flux vidéos HLS (.m3u8 / .ts) stockés sur S3.

Stockage : Garage S3 pour le stockage objet.

Base de données : PostgreSQL pour les métadonnées et Redis pour la file d'attente des tâches d'encodage.

Worker : Script Python intégrant FFmpeg pour transcoder les sources en HLS.

Administration : Arcane pour le monitoring et la gestion des conteneurs en local.

Comment lancer le projet

Initialiser la configuration :
Il faut copier le fichier d'environnement et le remplir avec les identifiants de la base de données.

cp .env.exemple .env


Lancer les services :

docker compose up --build -d


Accès aux interfaces (temporaire):

Web (Player) : http://localhost:3000

Arcane (Dashboard) : http://localhost:3552

S3 API : http://localhost:3900

Notes et Galères rencontrées

Problème de droits avec Nginx en mode non-root :
J'ai eu un blocage sur les images Nginx Alpine qui refusaient de démarrer à cause d'une erreur "Permission denied" sur le fichier /run/nginx.pid. L'utilisateur nginx n'ayant pas les droits d'écriture à cet emplacement par défaut. J'ai réglé le problème en ajoutant une commande sed dans les Dockerfiles (frontend et streaming) pour rediriger l'écriture du PID vers /tmp/nginx.pid directement dans le fichier de configuration global.

Intégration de Jellyfin :
L'objectif suivant est d'ajouter Jellyfin à la stack pour gérer la bibliothèque VOD. Le défi technique est que Jellyfin attend un stockage fichier local et ne gère pas nativement le S3. La solution prévue est de monter le bucket Garage S3 dans le conteneur Jellyfin en utilisant rclone, afin de faire le pont entre le stockage objet et le système de fichiers classique.