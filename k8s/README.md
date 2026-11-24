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
- Les 3 VM tournent sur un hôte Proxmox, sur un pont interne (`vmbr1`, `192.168.100.0/24`).
  Le Proxmox (`192.168.100.254`) sert de passerelle et fait le NAT vers Internet.

## Adresses

| Usage                        | IP / plage                           |
|------------------------------|--------------------------------------|
| VIP de l'API (kube-vip)      | 192.168.100.10                       |
| Pool MetalLB                 | 192.168.100.200 - 192.168.100.220    |
| Traefik (point d'entrée web) | 192.168.100.201                      |
| Jellyfin                     | https://jelly.192.168.100.201.nip.io |

Les noms de domaine utilisent nip.io (`jelly.192.168.100.201.nip.io` se résout en `192.168.100.201`).

## Accès depuis un poste extérieur

Le réseau des VM n'est joignable qu'à travers le Proxmox :

- **SSH** : rebond par le Proxmox (`ssh -J root@<IP_PROXMOX> user@192.168.100.12`,
  ou `ProxyJump` dans `~/.ssh/config`).
- **Web** : tunnel SSH vers Traefik, par exemple `LocalForward 8443 192.168.100.201:443`,
  plus une entrée `127.0.0.1 jelly.192.168.100.201.nip.io` dans `/etc/hosts`, puis
  `https://jelly.192.168.100.201.nip.io:8443`.
- **Interface Longhorn** (sans authentification, jamais exposée) :
  `kubectl -n longhorn-system port-forward svc/longhorn-frontend 8080:80` sur un nœud,
  puis tunnel SSH vers ce port.

## Composants

| Composant    | Rôle                                                               | Version             |
|--------------|--------------------------------------------------------------------|---------------------|
| kube-vip     | IP virtuelle haute dispo pour l'API Kubernetes                     | v1.3.1              |
| MetalLB      | IP externes pour les Services `LoadBalancer` (mode L2)             | chart 0.16.2        |
| Traefik      | Ingress controller : routage HTTP/HTTPS par domaine, 2 réplicas    | chart 42.4.0 (v3.7) |
| cert-manager | Génère les certificats TLS (ClusterIssuer auto-signé)              | v1.21.3             |
| Longhorn     | Stockage persistant répliqué (StorageClass par défaut, 2 réplicas) | v1.12.2             |
| Jellyfin     | Serveur de streaming (image linuxserver, figée par digest)         | 12.4.0              |

Chemin d'une requête :

    PC → Proxmox → 192.168.100.201 (MetalLB) → Traefik (TLS) → Service jellyfin → pod Jellyfin

## Arborescence

    k8s/
    ├── kube-vip/       manifest du pod statique (copie de référence)
    ├── metallb/        pool d'IP + annonce L2
    ├── traefik/        values Helm
    ├── cert-manager/   values Helm + ClusterIssuer
    ├── longhorn/       values Helm + test de volume RWO (test-rwo.yaml)
    ├── whoami/         test de validation Ingress + TLS (namespace demo, jetable)
    └── jellyfin/       namespace, PVC, Deployment, Service, Ingress

## Réinstallation (depuis k8s-2, utilisateur `user`)

Variables utilisées : `source ~/tp.env` (`TRAEFIK_IP`, `SHOP_DOMAIN`, `LONGHORN_VERSION`…).

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

    # Jellyfin
    kubectl apply -f k8s/jellyfin/00-namespace.yaml
    kubectl apply -f k8s/jellyfin/10-pvc.yaml -f k8s/jellyfin/20-deployment.yaml -f k8s/jellyfin/30-service.yaml
    envsubst < k8s/jellyfin/40-ingress.yaml | kubectl apply -f -

## Tests de validation

- **MetalLB** : un Service `LoadBalancer` reçoit une IP du pool et répond depuis le réseau.
- **Ingress + TLS (whoami)** : 3 réplicas derrière Traefik, certificat émis par cert-manager.

      kubectl create namespace demo
      envsubst < k8s/whoami/whoami.yaml | kubectl apply -n demo -f -
      kubectl -n demo get certificate        # READY True
      for i in 1 2 3 4 5 6; do curl -sk https://whoami.${TRAEFIK_IP}.nip.io | grep Hostname; done
      kubectl delete namespace demo

  Résultat : les 3 pods répondent à tour de rôle → répartition de charge L7 + HTTPS fonctionnels.

- **Volume Longhorn RWO** (`k8s/longhorn/test-rwo.yaml`) : un pod écrit dans un volume, on le supprime
  puis on le recrée : la ligne écrite par l'ancien pod est toujours là. Supprimer le PVC détruit
  le volume (`reclaimPolicy: Delete`).

## Application : Jellyfin

Namespace `jellyfin`, accessible sur `https://jelly.192.168.100.201.nip.io`.

Choix techniques :

- **Deployment à 1 réplica, stratégie `Recreate`** : Jellyfin utilise une base SQLite, qui ne supporte
  pas deux instances simultanées. `Recreate` arrête l'ancien pod avant de lancer le nouveau.
- **Config sur PVC Longhorn RWO** (`jellyfin-config`, 5 Gi, 2 réplicas) : comptes, bibliothèques, base.
- **Médias sur PVC Longhorn RWO** (`jellyfin-media`, 10 Gi) : solution provisoire. Dans la version
  Docker, les médias sont dans Garage (S3) et montés par Rclone (FUSE) : cette intégration reste à faire.
- **Image figée par digest** (`lscr.io/linuxserver/jellyfin@sha256:b1004…cb58`, Jellyfin 12.4.0) :
  linuxserver ne publie pas d'étiquette `12.4.0`, et `:latest` rendrait le déploiement non reproductible
  (`imagePullPolicy: Always`, mise à jour non maîtrisée).
- **Probes** sur `/health` : Traefik n'envoie du trafic qu'à un Jellyfin prêt, et un Jellyfin bloqué est redémarré.
- **Ressources** : `requests` 250m / 512 Mi, `limits` 2 CPU / 2 Gi.

Test de persistance (23/11) : avant suppression du pod, `ServerName: Jellyfin` et
`StartupWizardCompleted: true`. Le nouveau pod (`jellyfin-64c86bcd86-7f8nt`, démarré sur k8s-1) affiche
les mêmes valeurs, et le compte administrateur fonctionne sans repasser par l'assistant.

## Choix de versions et écarts aux documentations

| Sujet                                  | Choix retenu                                              | Raison                                |
|----------------------------------------|-----------------------------------------------------------|---------------------------------------|
| Ingress controller                     | Traefik plutôt qu'ingress-nginx                           | ingress-nginx en fin de vie           |
| `service.type` dans les values Traefik | Supprimé (`service.spec.type`, `LoadBalancer` par défaut) | Schéma du chart Traefik 42            |
| Vérification des prérequis Longhorn    | `longhornctl check preflight`                             | `environment_check.sh` supprimé depuis Longhorn 1.9.0 |
| Version de Longhorn                    | v1.12.2                                                   | Les versions 1.9.x ne supportent pas Kubernetes 1.37 |
| `export ETCDCTL_API=3`                 | Inutile                                                   | Ignorée en etcd 3.7 (l'API v2 n'existe plus) |

## Points d'attention (retours d'expérience)

- **Swap** : désactivé de façon persistante sur les 3 nœuds (ligne commentée dans `/etc/fstab`).
  Sinon, au redémarrage, le kubelet refuse de démarrer et tout le cluster tombe (incident du 13/11).
- **kube-vip** : sur les nœuds ajoutés par `kubeadm join`, le manifest doit pointer sur `admin.conf`
  et non sur `super-admin.conf`, qui n'existe que sur le premier nœud.
- **kubeconfig** : l'erreur `localhost:8080 refused` veut dire que l'utilisateur courant n'a pas de
  `~/.kube/config`. Il faut y copier `/etc/kubernetes/admin.conf`.
- **DNS** : une coupure DNS a bloqué le téléchargement des images Longhorn sur k8s-2 (incident du 23/11).
  Corrigé : DNS principal + secours dans `/etc/systemd/resolved.conf.d/k8s-dns.conf` sur les 3 nœuds.
- **MetalLB et kubeadm** : kubeadm pose l'étiquette `node.kubernetes.io/exclude-from-external-load-balancers`
  sur les control-planes. Avec 3 nœuds mixtes, plus aucun nœud n'annonçait les IP MetalLB (ARP sans réponse
  depuis l'extérieur, alors que les tests lancés depuis un nœud passaient). Corrigé par
  `kubectl label nodes --all node.kubernetes.io/exclude-from-external-load-balancers-`.
- **Longhorn** : `multipathd` peut bloquer le montage des volumes. Le désactiver si le preflight le signale.
- **Snapshots Proxmox** : avec « Include RAM », chaque snapshot sauvegarde 14 à 16 Go par VM et prend
  ~15 min. Une sauvegarde interrompue laisse QEMU bloqué (`savevm-end`) : il faut arrêter complètement la VM.
  Préférer des snapshots sans RAM.
- **kubectl delete** : pour supprimer des ressources de types différents en une commande, préfixer chaque
  nom par son type (`kubectl delete pod/test-writer pvc/test-rwo`).
- **YAML** : l'indentation se perd au copier-coller depuis un PDF ou une page web. Toujours passer par
  un fichier du dépôt (espaces uniquement, jamais de tabulations).
- **Secrets** : rien de sensible dans le dépôt (voir `.gitignore`). Les secrets iront dans des `Secret` Kubernetes.

## Sauvegardes

- **Snapshot etcd** (23/11) : `etcdctl snapshot save` sur k8s-2 (etcd 3.7.0), 21 Mo, 1031 clés,
  vérifié avec `etcdutl snapshot status`, copié hors du nœud (empreinte SHA-256 comparée).
  Le snapshot contient les objets Kubernetes, mais ni les données des volumes, ni les certificats,
  ni la configuration des nœuds, ni les images. Un namespace témoin `marqueur-avant` a été créé
  juste avant, pour prouver une éventuelle restauration.
- **Snapshot Longhorn** (23/11) : snapshot du volume `jellyfin-config`, création d'un fichier
  `casse.txt`, puis retour arrière (Jellyfin arrêté avec `scale --replicas=0`, volume attaché en
  mode maintenance, Revert depuis la frise, Detach, `scale --replicas=1`). Le fichier a disparu,
  la configuration de Jellyfin est intacte. Un snapshot reste sur les disques du cluster : il ne
  protège pas d'une perte totale, contrairement à un backup vers une cible externe.
- **Snapshots Proxmox** des 3 VM avant les tests de panne (point de retour rapide).

## Tests de panne

Poste d'observation, hors du cluster (sur le Proxmox) :

- `ha-probe.sh` : interroge `https://jelly.192.168.100.201.nip.io/health` chaque seconde (code HTTP + temps) ;
- une boucle de `ping` sur la VIP de l'API (`192.168.100.10`) ;
- pour le test de perte du quorum, une boucle `kubectl get nodes` sur le nœud survivant (`API OK` / `API KO`).

Les arrêts sont faits avec **Stop** dans Proxmox (coupure brutale, comme une panne de courant).

### Arrêt brutal du nœud qui héberge Jellyfin (k8s-1)

État initial : Jellyfin et l'annonce MetalLB de `.201` sur k8s-1, VIP sur k8s-3.

| Heure | Événement |
|-------|-----------|
| ~16:09 | Stop de k8s-1 : l'annonce de `.201` passe sur k8s-3 en quelques secondes |
| ~16:09 | k8s-1 passe `NotReady` ; Traefik répond `503` (plus de pod Jellyfin prêt) |
| 16:14:41 | Le pod est évincé (5 min plus tard), un nouveau pod est créé sur k8s-3 |
| ~16:15 | Longhorn rattache le volume à k8s-3, Jellyfin redémarre, retour des `200` |

Coupure de Jellyfin : environ 6 minutes. L'éviction n'est pas immédiate : chaque pod tolère
les taints `node.kubernetes.io/unreachable` et `not-ready` pendant 300 s. Kubernetes attend ce délai
pour ne pas déplacer les pods à la moindre coupure réseau passagère, ce qui est d'autant plus
important pour un volume RWO, qui ne peut pas être monté sur deux nœuds à la fois.

### Arrêt du nœud qui porte la VIP de l'API (k8s-3)

VIP injoignable pendant environ **20 secondes** (17:22:35 → 17:22:55), puis reprise par un autre nœud.
Ce délai cumule l'expiration du bail kube-vip (Lease `plndr-cp-lock`), une éventuelle élection du leader
etcd, et la mise à jour du cache ARP via un gratuitous ARP. Pendant ce temps, `kubectl` ne répond plus,
mais les applications ne sont pas touchées par la perte de la VIP. Jellyfin, hébergé sur k8s-3, a suivi
la même séquence que lors de l'arrêt de k8s-1.

### Perte du quorum etcd (k8s-2 et k8s-3 arrêtés, k8s-1 survivant)

- etcd n'a plus que 1 membre sur 3 : l'API devient inutilisable (`API KO`), `kubectl` ne fonctionne plus.
- Jellyfin répond **environ une requête sur deux** : kube-proxy sur k8s-1 continue de répartir le trafic
  entre les deux copies de Traefik, dont celle du nœud éteint. Sans API, personne ne peut retirer
  cette destination morte.
- Conclusion : sans quorum, le cluster est **figé**. Les applications déjà lancées tournent sur leur
  configuration en mémoire, mais plus rien ne s'auto-répare (pas d'éviction, pas de recréation de pod,
  pas de mise à jour des endpoints).
- Au redémarrage de k8s-2, etcd retrouve 2 membres sur 3 et l'API repart **sans aucune intervention**.

### Observation imprévue : après un redémarrage brutal

Après un Stop puis un Start de k8s-1, le pod Jellyfin est resté en `Unknown` puis bloqué au montage :
le pilote CSI de Longhorn (`driver.longhorn.io`) n'était pas encore enregistré sur le nœud, puis les
volumes n'étaient pas encore rattachés. Supprimer le pod a permis à un nouveau pod de repartir proprement.

## Reste à faire
- [ ] Médias servis par Garage (StatefulSet) + Rclone (montage FUSE), comme dans la version Docker
- [ ] Migration des VM vers un autre hôte Proxmox (scripts de bootstrap)
- [ ] Bonus : monitoring, GitOps
