ARG ARGOCD_VERSION="v2.6.7"
ARG K9S_VERSION="v0.26.7"
ARG TAILSCALE_VERSION="v1.44.0"
ARG CLOUDFLARED_VERSION="2023.8.2"

FROM ghcr.io/tailscale/tailscale:${TAILSCALE_VERSION} as tailscale
FROM quay.io/derailed/k9s:${K9S_VERSION} as k9s
FROM docker.io/envcli/kubectx as kx
FROM docker.io/cloudflare/cloudflared:${CLOUDFLARED_VERSION} as cloudflared

FROM mcr.microsoft.com/vscode/devcontainers/base:ubuntu-22.04

# Add google cloud sdk repo
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/atp/doc/apt-key.gpg | sudo tee /usr/share/keyrings/cloud.google.gpg

# Apt Package Install
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    musl fzf htop jq golang-go gnupg \
    inetutils-ping dnsutils python3-pip \
    google-cloud-cli 

# Install cloudflared CLI
COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared

# Install kubectx and kubens shortcuts
COPY --from=kx /usr/local/bin/kubectx /usr/local/bin/kubectx
COPY --from=kx /usr/local/bin/kubens /usr/local/bin/kubens

# Install tailscale
COPY --from=tailscale /usr/local/bin/tailscale /usr/local/bin/tailscale
COPY --from=tailscale /usr/local/bin/tailscaled /usr/local/bin/tailscaled

# Install k9s CUI and use bundled kubectl
COPY --from=k9s /bin/k9s /usr/local/bin/k9s
COPY --from=k9s /usr/local/bin/kubectl /usr/bin/kubectl

# Install argocd CLI and use bundled kustomize+helm
COPY --from=argocd /usr/local/bin/argocd /usr/bin/argocd
COPY --from=argocd /usr/local/bin/kustomize /usr/bin/kustomize
COPY --from=argocd /usr/local/bin/helm /usr/bin/helm