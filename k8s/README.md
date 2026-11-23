# Déploiement Kubernetes

Migration de la stack Docker (`compose.yaml`) vers un cluster Kubernetes de 3 nœuds.
Base : TP « WordPress kubeadm », adapté au projet Jellyfin et aux versions actuelles des outils.

## Architecture

| Nœud  | IP             | Rôle                                                        |
|-------|----------------|-------------------------------------------------------------|
| k8s-1 | 192.168.100.11 | control-plane + worker                                      |
| k8s-2 | 192.168.100.12 | control-plane + worker, **nœud admin** (kubectl, helm, git) |
| k8s-3 | 192.168.100.13 | control-plane + worker                                      |

- Kubernetes v1.37.1 (kubeadm), containerd, CNI Calico
- etcd empilé sur les 3 nœuds → tolère la perte d'un nœud (quorum 2/3)
- Le taint `control-plane` est retiré : les applications tournent sur les 3 nœuds

## Adresses

| Usage                        | IP / plage                        |
|------------------------------|-----------------------------------|
| VIP de l'API (kube-vip)      | 192.168.100.10                    |
| Pool MetalLB                 | 192.168.100.200 - 192.168.100.220 |
| Traefik (point d'entrée web) | 192.168.100.201                   |

Les postes clients sont sur un autre VLAN : l'accès passe par le routage inter-VLAN.
Les noms de domaine utilisent nip.io, par exemple `jelly.192.168.100.201.nip.io`.

## Composants

| Composant    | Rôle                                                               | Version             |
|--------------|--------------------------------------------------------------------|---------------------|
| kube-vip     | IP virtuelle haute dispo pour l'API Kubernetes                     | v1.3.1              |
| MetalLB      | IP externes pour les Services `LoadBalancer` (mode L2)             | chart 0.16.2        |
| Traefik      | Ingress controller : routage HTTP/HTTPS par domaine, 2 réplicas    | chart 42.4.0 (v3.7) |
| cert-manager | Génère les certificats TLS (ClusterIssuer auto-signé)              | v1.21.3             |
| Longhorn     | Stockage persistant répliqué (StorageClass par défaut, 2 réplicas) | v1.12.2             |
| Jellyfin     | Serveur de streaming                                               | à venir             |

Chemin d'une requête :

    PC → routeur inter-VLAN → 192.168.100.201 (MetalLB) → Traefik (TLS) → Service → pod

## Arborescence

    k8s/
    ├── kube-vip/       manifest du pod statique (copie de référence)
    ├── metallb/        pool d'IP + annonce L2
    ├── traefik/        values Helm
    ├── cert-manager/   values Helm + ClusterIssuer
    ├── longhorn/       values Helm
    ├── whoami/         test de validation Ingress + TLS (namespace demo, jetable)
    └── jellyfin/       à venir

## Réinstallation (depuis k8s-2, utilisateur `user`)

Variables utilisées : `source ~/tp.env` (`TRAEFIK_IP`, `LONGHORN_VERSION`…).

    # MetalLB
    helm repo add metallb https://metallb.github.io/metallb
    helm install metallb metallb/metallb -n metallb-system --create-namespace
    kubectl apply -f k8s/metallb/metallb-config.yaml

    # Traefik
    helm repo add traefik https://traefik.github.io/charts
    helm install traefik traefik/traefik -n traefik --create-namespace -f k8s/traefik/traefik-values.yaml

    # cert-manager
    helm repo add jetstack https://charts.jetstack.io
    helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace -f k8s/cert-manager/cert-manager-values.yaml
    kubectl apply -f k8s/cert-manager/clusterissuer.yaml

    # Longhorn (prérequis : open-iscsi, nfs-common, cryptsetup, dmsetup sur les 3 nœuds)
    helm repo add longhorn https://charts.longhorn.io
    helm install longhorn longhorn/longhorn -n longhorn-system --create-namespace \
      --version ${LONGHORN_VERSION#v} -f k8s/longhorn/longhorn-values.yaml

## Tests de validation

- **MetalLB** : un Service `LoadBalancer` reçoit une IP du pool et répond depuis le réseau.
- **Ingress + TLS (whoami)** : 3 réplicas derrière Traefik, certificat émis par cert-manager.

      kubectl create namespace demo
      envsubst < k8s/whoami/whoami.yaml | kubectl apply -n demo -f -
      kubectl -n demo get certificate        # READY True
      for i in 1 2 3 4 5 6; do curl -sk https://whoami.${TRAEFIK_IP}.nip.io | grep Hostname; done
      kubectl delete namespace demo

  Résultat : les 3 pods répondent à tour de rôle → répartition de charge L7 + HTTPS fonctionnels.

## Adaptations par rapport au TP

| Sujet du TP                            | Adaptation                                                | Raison                                |
|----------------------------------------|-----------------------------------------------------------|---------------------------------------|
| ingress-nginx (envisagé)               | Traefik                                                   | ingress-nginx en fin de vie           |
| `service.type` dans les values Traefik | Supprimé (`service.spec.type`, `LoadBalancer` par défaut) | Schéma du chart Traefik 42            |
| `environment_check.sh` (Longhorn)      | `longhornctl check preflight`                             | Script supprimé depuis Longhorn 1.9.0 |
| Longhorn v1.9.1                        | Longhorn v1.12.2                                          | 1.9.x ne supporte pas Kubernetes 1.37 |

## Points d'attention (retours d'expérience)

- **Swap** : désactivé de façon persistante sur les 3 nœuds (ligne commentée dans `/etc/fstab`).
  Sinon, au redémarrage, le kubelet refuse de démarrer et tout le cluster tombe (incident du 13/11).
- **kube-vip** : sur les nœuds ajoutés par `kubeadm join`, le manifest doit pointer sur `admin.conf`
  et non sur `super-admin.conf`, qui n'existe que sur le premier nœud.
- **kubeconfig** : l'erreur `localhost:8080 refused` veut dire que l'utilisateur courant n'a pas de
  `~/.kube/config`. Il faut y copier `/etc/kubernetes/admin.conf`.
- **DNS** : un seul serveur DNS par nœud = point de défaillance. Une coupure DNS a bloqué le
  téléchargement des images Longhorn sur k8s-2 (incident du 23/11). Prévoir un DNS de secours.
- **Longhorn** : `multipathd` peut bloquer le montage des volumes. Le désactiver si le preflight le signale.
- **YAML** : l'indentation se perd au copier-coller depuis le PDF. Toujours passer par un fichier
  du dépôt (espaces uniquement, jamais de tabulations).
- **Secrets** : rien de sensible dans le dépôt (voir `.gitignore`). Les secrets iront dans des `Secret` Kubernetes.

## Reste à faire

- [ ] DNS de secours sur les 3 nœuds
- [ ] Stockage des médias (volume partagé) et de la config Jellyfin
- [ ] Déploiement de Jellyfin (1 réplica, stratégie `Recreate`) + Ingress
- [ ] Migration de Garage
- [ ] Sauvegardes et tests de panne (modules 11-12 du TP)
- [ ] Bonus : monitoring, GitOps
