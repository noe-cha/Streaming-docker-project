# Projet Ynov+ - Architecture VOD

Ce dépôt contient l'infrastructure de notre projet de streaming vidéo, basé sur une architecture microservices avec Docker Compose. Le projet est conçu pour être migré sur Kubernetes par la suite.

## Architecture technique
- **Frontend** : Interface utilisateur web (HTML/JS) avec lecteur HLS.
- **Streaming (Nginx)** : Serveur configuré pour distribuer les flux vidéo.
- **Worker (Python/FFmpeg)** : Service asynchrone pour l'encodage vidéo.
- **MinIO** : Stockage objet compatible S3 pour les médias.
- **Redis** : Broker de messages pour la file d'attente d'encodage.
- **PostgreSQL** : Base de données relationnelle.
- **Portainer** : Interface de supervision Docker.

## Lancement du projet en local

1. Cloner le projet :
   ```bash
   git clone [https://github.com/noe-cha/Streaming-docker-project.git](https://github.com/noe-cha/Streaming-docker-project.git)
   cd Streaming-docker-project
