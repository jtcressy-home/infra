# Bootstrapping

incase your shit got fucked and you have to build the cluster from scratch again, here's what you gotta do to light the fire again:

```
kustomize build kubernetes/clusters/bastion/cni --enable-helm | kaf -
kustomize build kubernetes/deploy/admin/argocd/argocd/clusters/bastion --enable-helm | kaf -
kaf kubernetes/argocd/static-apps/root.yaml
kaf kubernetes/argocd/projects/admin.yaml
k create secret generic op-credentials -n external-secrets --from-literal=1password-credentials.json=$(op read op://jtcressy-net-infra/op-connect-credentials_core-cluster/1password-credentials.json | base64) --from-literal=eso-token=$(op read op://jtcressy-net-infra/op-connect-token_core-cluster_eso-core-cluster/credential)
```

if shit's _really_ fucked and you don't have the op-connect credentials in 1password anymore, just create a new secrets automation integration so you get a new 1password-credentials.json and a token for external-secrets operator. Load the .json into a document item in 1password and keep the filename the same, then save the token as a separate password item (only use the password field).

maybe by the time you are reading this in the future and your cluster is inevitably fucked again, external-secrets will support 1password service account tokens and you can refactor this setup to work with that. hopefully. they're a much cleaner implementation, and don't require a connect server.