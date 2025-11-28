ARG ARGOCD_VERSION="v3.2.0"
ARG K9S_VERSION="latest"
ARG TAILSCALE_VERSION="v1.90.9"
ARG CLOUDFLARED_VERSION="2025.11.1"
ARG TALOSCTL_VERSION="v1.11.5"

FROM ghcr.io/tailscale/tailscale:${TAILSCALE_VERSION} as tailscale
FROM docker.io/derailed/k9s:${K9S_VERSION} as k9s
FROM quay.io/argoproj/argocd:${ARGOCD_VERSION} as argocd
FROM docker.io/envcli/kubectx as kx
FROM docker.io/cloudflare/cloudflared:${CLOUDFLARED_VERSION} as cloudflared
FROM ghcr.io/siderolabs/talosctl:${TALOSCTL_VERSION} as talosctl
FROM docker.io/mikefarah/yq:latest as yq

FROM golang:1.25 as gomod-builder

ENV GOBIN /usr/local/bin

# Install taskfile CLI
RUN go install github.com/go-task/task/v3/cmd/task@latest

# Install fzf
RUN go install github.com/junegunn/fzf@0.46.1

############################################

FROM mcr.microsoft.com/vscode/devcontainers/base:ubuntu

# Add google cloud sdk repo
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo tee /usr/share/keyrings/cloud.google.asc

# Add doppler repo
RUN curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | sudo gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/doppler-cli.list


# Apt Package Install
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    musl htop jq golang-go gnupg \
    inetutils-ping dnsutils python3-pip \
    google-cloud-cli doppler restic

# Ensure restic is up to date
RUN restic self-update

# Copy binaries from gomod-builder
COPY --from=gomod-builder /usr/local/bin/* /usr/local/bin/

# Install talhelper
RUN curl https://i.jpillora.com/budimanjojo/talhelper! | sudo bash

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

# Install talosctl
COPY --from=talosctl /talosctl /usr/local/bin/talosctl

# Install yq
COPY --from=yq /usr/bin/yq /usr/bin/yq