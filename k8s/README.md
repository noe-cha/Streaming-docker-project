# Déploiement Kubernetes

Migration de la stack Docker (`compose.yaml`) vers un cluster Kubernetes de 3 nœuds pour mise en place d'une infrastructure Jellyfin.

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
- **MetalLB et kubeadm** : kubeadm pose l'étiquette `node.kubernetes.io/exclude-from-external-load-balancers`
  sur les control-planes. Avec 3 nœuds mixtes, plus aucun nœud n'annonçait les IP MetalLB (ARP sans réponse
  depuis l'extérieur, alors que les tests lancés depuis un nœud passaient). Corrigé par
  `kubectl label nodes --all node.kubernetes.io/exclude-from-external-load-balancers-`.
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

Résultat du test (23/11) : avant suppression, `ServerName: Jellyfin` et `StartupWizardCompleted: true`.
Le nouveau pod (`jellyfin-64c86bcd86-7f8nt`, démarré sur k8s-1) affiche les mêmes valeurs, et le compte
administrateur fonctionne sans repasser par l'assistant. 

## Sauvegardes

- **Snapshot etcd** (23/11) : `etcdctl snapshot save` sur k8s-2 (etcd 3.7.0), 21 Mo, 1031 clés,
  vérifié avec `etcdutl snapshot status`, copié hors du nœud (empreinte SHA-256 comparée).
  Le snapshot contient les objets Kubernetes, pas les données des volumes, ni les certificats,
  ni la configuration des nœuds, ni les images (Q13).
  Note : `ETCDCTL_API=3` est ignorée en etcd 3.7 (l'API v2 n'existe plus).
- **Snapshot Longhorn** (23/11) : snapshot du volume `jellyfin-config`, création d'un fichier
  `casse.txt`, puis retour arrière (Jellyfin arrêté avec `scale --replicas=0`, volume attaché en
  mode maintenance, Revert depuis la frise, Detach, `scale --replicas=1`). Le fichier a disparu,
  la configuration de Jellyfin est intacte. Un snapshot reste sur les disques du cluster : il ne
  protège pas d'une perte totale (Q14), contrairement à un backup vers une cible externe.

## Tests de panne
Poste d'observation, hors du cluster (sur le PVE) :

- `ha-probe.sh` : interroge `https://jelly.192.168.100.201.nip.io/health` chaque seconde (code HTTP + temps) ;
- une boucle de `ping` sur la VIP de l'API (`192.168.100.10`) ;
- pour P5, une boucle `kubectl get nodes` sur le nœud survivant (`API OK` / `API KO`).

Les arrêts sont faits avec **Stop** dans Proxmox (coupure brutale, comme une panne de courant).

### P1 : arrêt brutal du nœud qui héberge Jellyfin (k8s-1)

État initial : Jellyfin et l'annonce MetalLB de `.201` sur k8s-1, VIP sur k8s-3.

| Heure | Événement |
|-------|-----------|
| ~16:09 | Stop de k8s-1 : l'annonce de `.201` passe sur k8s-3 en quelques secondes |
| ~16:09 | k8s-1 passe `NotReady` ; Traefik répond `503` (plus de pod Jellyfin prêt) |
| 16:14:41 | Le pod est évincé (5 min plus tard), un nouveau pod est créé sur k8s-3 |
| ~16:15 | Longhorn rattache le volume à k8s-3, Jellyfin redémarre, retour des `200` |

Coupure de Jellyfin : environ 6 minutes. L'éviction n'est pas immédiate (Q15) : chaque pod tolère
les taints `node.kubernetes.io/unreachable` et `not-ready` pendant 300 s. Kubernetes attend ce délai
pour ne pas déplacer les pods à la moindre coupure réseau passagère, ce qui est d'autant plus
important pour un volume RWO, qui ne peut pas être monté sur deux nœuds à la fois.

### P3 : arrêt du nœud qui porte la VIP de l'API (k8s-3)

VIP injoignable pendant environ **20 secondes** (17:22:35 → 17:22:55), puis reprise par un autre nœud.
Ce délai cumule l'expiration du bail kube-vip (Lease `plndr-cp-lock`), une éventuelle élection du leader
etcd, et la mise à jour du cache ARP via un gratuitous ARP. Pendant ce temps, `kubectl` ne répond plus,
mais les applications ne sont pas touchées par la perte de la VIP. Jellyfin, hébergé sur k8s-3, a suivi
la même séquence que P1.

### P5 : perte du quorum etcd (k8s-2 et k8s-3 arrêtés, k8s-1 survivant)

- etcd n'a plus que 1 membre sur 3 : l'API devient inutilisable (`API KO`), `kubectl` ne fonctionne plus.
- Jellyfin répond **environ une requête sur deux** : kube-proxy sur k8s-1 continue de répartir le trafic
  entre les deux copies de Traefik, dont celle du nœud éteint. Sans API, personne ne peut retirer
  cette destination morte.
- Conclusion (Q16) : sans quorum, le cluster est **figé**. Les applications déjà lancées tournent sur leur
  configuration en mémoire, mais plus rien ne s'auto-répare (pas d'éviction, pas de recréation de pod,
  pas de mise à jour des endpoints).
- Au redémarrage de k8s-2, etcd retrouve 2 membres sur 3 et l'API repart **sans aucune intervention**.

### Observation imprévue : après un redémarrage brutal

Après un Stop puis un Start de k8s-1, le pod Jellyfin est resté en `Unknown` puis bloqué au montage :
le pilote CSI de Longhorn (`driver.longhorn.io`) n'était pas encore enregistré sur le nœud, puis les
volumes n'étaient pas encore rattachés. Supprimer le pod a permis à un nouveau pod de repartir proprement.
