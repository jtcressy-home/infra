# Kubernetes Folder Structure


### Example Structure
```
.
├── <namespace>
│   └── <app-name>
│       ├── base
│       ├── clusters
│       │   └── <cluster-name>
│       └── components
└── my-other-namespace
    ├── my-cluster-addon-app
    │   ├── base
    │   ├── clusters
    │   │   ├── __all__
    │   │   ├── my-cluster
    │   │   └── my-other-cluster
    │   └── components
    └── my-other-app
        └── my-cluster
```

### General Rules
- Folders will follow `<namespace>/<app-name>/clusters/<cluster-name>`
- An ArgoCD ApplicationSet will generate an Application for every `<namespace>` (impl. at `kubernetes/argocd/appsets/clusters/core/namespaces-appset.yaml`)
  - This application creates ONLY the following:
    - `Namespace` object matching the namespace name
    - `AppProject` object matching the namespace name and allowing deployment to the same namespace
- An ArgoCD ApplicationSet will generate an Application for every `<namespace>/<app-name>/clusters/<cluster-name>` (impl. at `kubernetes/argocd/appsets/clusters/core/clusterapps-appset.yaml`)
  - `.spec.project` of the generated application will match the `<namespace>`
  - `.spec.destination.name` of the generated application will match the `<cluster-name>`
  - `.spec.destination.namespace` of the generated application will match the `<namespace>`
  - Application name will have the format `<app-name>-<cluster-name>` in case the app is deployed to multiple clusters
  - ApplicationSet will SKIP paths matching `<namespace>/<app-name>/clusters/__all__` to be handled by a different ApplicationSet
- An ArgoCD ApplicationSet will generate an Application for every  `<namespace>/<app-name>/clusters/__all__` and connected cluster (impl. at `kubernetes/argocd/appsets/clusters/core/allclusters-appset.yaml`)
  - `.spec.project` of the generated application will match the `<namespace>`
  - `.spec.destination.namespace` of the genertaed application will match the `<namespace>`
  - `.spec.destination.name` of the generated application will match one of the connected clusters
  - Application name will have the format `<app-name>-<cluster-name>`
  - Intended for use by apps that are considered cluster-addons and do not require cluster-specific configuration. i.e. "One size fits all"

### ArgoCD Bootstrapping against `core` cluster
1. Create argocd namespace `kubectl create namespace argocd`
2. Apply the application overlay `kubectl apply -k ./kubernetes/argocd/argocd/clusters/core`
3. Apply the namespace overlay `kubectl apply -k ./kubernetes/argocd` (depends on the AppProject CRD from step 2)
4. Apply the appsets overlay `kubectl apply -k ./kubernetes/argocd/appsets/clusters/core`
5. Let ArgoCD reconcile and settle all applications