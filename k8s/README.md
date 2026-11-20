# Déploiement Kubernetes

Migration de la stack Docker (`compose.yaml`) vers un cluster Kubernetes de 3 nœuds.

## Architecture

| Nœud  | IP             | Rôle                                   |
|-------|----------------|----------------------------------------|
| k8s-1 | 192.168.100.11 | control-plane + worker                 |
| k8s-2 | 192.168.100.12 | control-plane + worker, **nœud admin** (kubectl, helm, git) |
| k8s-3 | 192.168.100.13 | control-plane + worker                 |

- Kubernetes v1.37.1 (kubeadm), containerd, CNI Calico
- etcd empilé sur les 3 nœuds → tolère la perte d'un nœud (quorum 2/3)
- Le taint `control-plane` est retiré : les applications tournent sur les 3 nœuds

## Adresses

| Usage                         | IP / plage                          |
|-------------------------------|-------------------------------------|
| VIP de l'API (kube-vip)       | 192.168.100.10                      |
| Pool MetalLB                  | 192.168.100.200 - 192.168.100.220   |
| Traefik (point d'entrée web)  | 192.168.100.201                     |

Les postes clients sont sur un autre VLAN : l'accès passe par le routage inter-VLAN.
Les noms de domaine utilisent nip.io, par exemple `jelly.192.168.100.201.nip.io`.

## Composants

| Composant    | Rôle                                                        | Version            |
|--------------|-------------------------------------------------------------|--------------------|
| kube-vip     | IP virtuelle haute dispo pour l'API Kubernetes              | v1.3.1             |
| MetalLB      | Fournit des IP externes aux Services `LoadBalancer` (L2)    | chart 0.16.2       |
| Traefik      | Ingress controller : route le HTTP/HTTPS selon le domaine   | chart 42.4.0 (v3.7)|
| cert-manager | Génère les certificats TLS (ClusterIssuer auto-signé)       | v1.21.3            |
| Jellyfin     | Serveur de streaming                                        | à venir            |

Chemin d'une requête :

    PC → routeur inter-VLAN → 192.168.100.201 (MetalLB) → Traefik → Service Jellyfin → pod

## Arborescence

    k8s/
    ├── kube-vip/       manifest du pod statique (copie de référence)
    ├── metallb/        pool d'IP + annonce L2
    ├── traefik/        values Helm (2 réplicas, anti-affinité)
    ├── cert-manager/   values Helm + ClusterIssuer
    └── jellyfin/       à venir

## Réinstallation (depuis k8s-2)

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

## Points d'attention (retours d'expérience)

- **Swap** : il doit être désactivé de façon persistante sur les 3 nœuds (ligne commentée dans `/etc/fstab`).
  Sinon, au redémarrage, le kubelet refuse de démarrer et tout le cluster tombe (incident du 13/11).
- **kube-vip** : sur les nœuds ajoutés par `kubeadm join`, le manifest doit pointer sur `admin.conf`
  et non sur `super-admin.conf`, qui n'existe que sur le premier nœud.
- **kubeconfig** : l'erreur `localhost:8080 refused` veut dire que l'utilisateur courant n'a pas de
  `~/.kube/config`. Il faut y copier `/etc/kubernetes/admin.conf`.
- **Secrets** : rien de sensible dans le dépôt (voir `.gitignore`). Les secrets iront dans des `Secret` Kubernetes.

## Reste à faire

- [ ] Stockage : médias (volume partagé) et config Jellyfin
- [ ] Déploiement de Jellyfin (1 réplica, stratégie `Recreate`) + Ingress
- [ ] Migration de Garage
- [ ] Bonus : monitoring, sauvegardes, GitOps
