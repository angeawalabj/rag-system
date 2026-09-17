# ADR-0008 — Structure Kustomize : base + overlays

| Champ       | Valeur                              |
|-------------|--------------------------------------|
| Statut      | **Accepté**                          |
| Date        | 2026-06-30                           |
| Tags        | k8s, kustomize, devops, infra        |

## Contexte

La v2 Kubernetes doit éviter la duplication YAML entre environnements (dev local k3s, prod cloud). Kustomize est retenu plutôt que Helm pour cette première itération k8s — Helm sera ajouté ensuite pour le packaging final (voir ADR-0009), mais Kustomize sert de base testable immédiatement, sans templating complexe.

## Décision

### Pourquoi Kustomize avant Helm

| Critère                    | Kustomize                  | Helm                        |
|------------------------------|-----------------------------|------------------------------|
| Courbe d'apprentissage      | Faible — YAML pur + patches | Moyenne — templating Go      |
| Déboguage                  | `kubectl kustomize` affiche le YAML final | Nécessite `helm template` |
| Adapté à un produit unique | ✅ Idéal                    | ⚠️ Sur-ingénierie pour 1 produit |
| Distribution publique       | ❌ Pas de packaging         | ✅ Chart partageable          |
| Intégré à kubectl           | ✅ Natif depuis 1.14         | ❌ Binaire séparé             |

Kustomize est utilisé pour les manifests de base (dev/prod). Helm est ajouté ensuite, uniquement pour offrir un chart installable en une commande (`helm install rag-system ./helm/rag-system`).

### Structure retenue

```
infra/k8s/
├── base/
│   ├── kustomization.yaml      ← liste les ressources + images par défaut
│   ├── namespace.yaml
│   ├── configmap.yaml          ← variables non sensibles
│   ├── secret.yaml.example     ← template — jamais commité avec valeurs réelles
│   ├── qdrant.yaml              StatefulSet + PVC + Service
│   ├── postgres.yaml            StatefulSet + PVC + Service
│   ├── redis.yaml                StatefulSet + PVC + Service
│   ├── ollama.yaml               Deployment + PVC + Service
│   ├── ingestion.yaml            Deployment + Service
│   ├── rag-api.yaml              Deployment + Service + HPA
│   └── frontend.yaml             Deployment + Service
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml   ← patches : 1 replica, resources réduites
    │   └── patches/
    └── prod/
        ├── kustomization.yaml   ← patches : HPA actif, PDB, resources prod
        └── patches/
```

### Principe de patch — exemple replicas

`base/rag-api.yaml` définit 2 replicas par défaut. `overlays/dev/kustomization.yaml` patch à 1 replica pour économiser les ressources locales :

```yaml
# overlays/dev/kustomization.yaml
patches:
  - target:
      kind: Deployment
      name: rag-api
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 1
```

### Gestion des secrets

Les vrais secrets (mots de passe PostgreSQL, etc.) ne sont **jamais** commités. `secret.yaml.example` sert de template ; le secret réel est généré par `scripts/k8s-secrets.sh` depuis `.env`, ou injecté via un secret manager externe (Sealed Secrets, External Secrets Operator) en v2.1.

## Conséquences

- **Positif** : `kubectl apply -k infra/k8s/overlays/dev` déploie l'environnement complet en une commande.
- **Positif** : Diff propre entre dev et prod — visible directement dans les fichiers de patch.
- **Négatif** : Moins de réutilisabilité externe qu'un chart Helm — adressé par le chart Helm (ADR-0009).
- **Point de vigilance** : Ollama nécessite potentiellement un `nodeSelector` GPU en prod — non géré par Kustomize seul, ajouté via patch JSON6902 dans l'overlay prod.
