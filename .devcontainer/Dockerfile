# See here for image contents: https://github.com/microsoft/vscode-dev-containers/tree/v0.224.3/containers/ubuntu/.devcontainer/base.Dockerfile

# [Choice] Ubuntu version (use hirsuite or bionic on local arm64/Apple Silicon): hirsute, focal, bionic
ARG VARIANT="jammy"
ARG TAILSCALE_VERSION=v1.30.2

FROM ghcr.io/tailscale/tailscale:${TAILSCALE_VERSION} as tailscale
FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:alpine as gcloud-sdk
FROM quay.io/derailed/k9s as k9s
FROM docker.io/envcli/kubectx as kx
FROM docker.io/cloudflare/cloudflared:2022.8.0 as cloudflared

FROM mcr.microsoft.com/vscode/devcontainers/base:0-${VARIANT}

# [Optional] Uncomment this section to install additional OS packages.
# RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
#     && apt-get -y install --no-install-recommends <your-package-list-here>

# Install Google Cloud SDK
ENV PATH $PATH:/usr/local/gcloud/google-cloud-sdk/bin
COPY --from=gcloud-sdk /google-cloud-sdk/ /usr/local/gcloud/google-cloud-sdk/

# Google Cloud SDK Setup
RUN gcloud components update && gcloud components install -q \
    gke-gcloud-auth-plugin nomos bq pkg kubectl kubectl-oidc kpt \
    terraform-tools skaffold kustomize docker-credential-gcr alpha beta

# Install ClusterCTL
RUN curl -L https://github.com/kubernetes-sigs/cluster-api/releases/latest/download/clusterctl-linux-amd64 -o /usr/local/bin/clusterctl \
    && chmod +x /usr/local/bin/clusterctl

# Install Helm
RUN curl -s https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash -

# Install doctl (DigitalOcean CLI)
ENV DOCTL_VERSION 1.72.0
RUN wget https://github.com/digitalocean/doctl/releases/download/v${DOCTL_VERSION}/doctl-${DOCTL_VERSION}-linux-amd64.tar.gz && \
    tar xf ./doctl-${DOCTL_VERSION}-linux-amd64.tar.gz && \
    mv ./doctl /usr/local/bin/doctl

COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared

COPY --from=kx /usr/local/bin/kubectx /usr/local/bin/kubectx
COPY --from=kx /usr/local/bin/kubens /usr/local/bin/kubens

COPY --from=tailscale /usr/local/bin/tailscale /usr/local/bin/tailscale
COPY --from=tailscale /usr/local/bin/tailscaled /usr/local/bin/tailscaled

COPY --from=k9s /bin/k9s /usr/local/bin/k9s


RUN curl -sLS https://get.k3sup.dev | sh && \
    k3sup version
