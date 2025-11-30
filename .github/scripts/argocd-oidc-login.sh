#!/usr/bin/env bash
set -euo pipefail

# Required environment variables
ARGOCD_SERVER="${ARGOCD_SERVER:?ARGOCD_SERVER environment variable is required}"
DEX_ISSUER="${DEX_ISSUER:-https://argocd.tailnet-4d89.ts.net/api/dex}"
GITHUB_OIDC_REQUEST_URL="${ACTIONS_ID_TOKEN_REQUEST_URL:?GitHub Actions OIDC token request URL not found}"
GITHUB_OIDC_REQUEST_TOKEN="${ACTIONS_ID_TOKEN_REQUEST_TOKEN:?GitHub Actions OIDC token not found}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Step 1: Obtain GitHub Actions OIDC Token
log_info "Requesting GitHub Actions OIDC token..."
GITHUB_OIDC_TOKEN=$(curl -sSf \
    -H "Authorization: Bearer ${GITHUB_OIDC_REQUEST_TOKEN}" \
    -H "Accept: application/json; api-version=2.0" \
    -H "Content-Type: application/json" \
    "${GITHUB_OIDC_REQUEST_URL}&audience=https://argocd.tailnet-4d89.ts.net" \
    | jq -r '.value')

if [[ -z "${GITHUB_OIDC_TOKEN}" || "${GITHUB_OIDC_TOKEN}" == "null" ]]; then
    log_error "Failed to obtain GitHub Actions OIDC token"
    exit 1
fi

log_info "GitHub OIDC token obtained successfully"

# Optional: Decode and display token claims for debugging
if [[ "${ACTIONS_STEP_DEBUG:-false}" == "true" ]]; then
    log_info "GitHub OIDC Token Claims:"
    echo "${GITHUB_OIDC_TOKEN}" | cut -d. -f2 | base64 -d 2>/dev/null | jq '.' >&2 || true
fi

# Step 2: Exchange GitHub OIDC token with Dex
# Use existing argo-cd-cli public client (no secret required)
log_info "Exchanging GitHub OIDC token with Dex using argo-cd-cli client..."

HTTP_CODE=$(curl -sS -w "%{http_code}" -o /tmp/dex_response.json \
    -X POST \
    "${DEX_ISSUER}/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "client_id=argo-cd-cli" \
    --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
    --data-urlencode "subject_token=${GITHUB_OIDC_TOKEN}" \
    --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:jwt" \
    --data-urlencode "connector_id=github-actions" \
    --data-urlencode "scope=openid groups email")

if [[ "${HTTP_CODE}" != "200" ]]; then
    log_error "Dex token exchange failed with HTTP ${HTTP_CODE}"
    log_error "Response: $(cat /tmp/dex_response.json)"
    rm -f /tmp/dex_response.json
    exit 1
fi

DEX_TOKEN_RESPONSE=$(cat /tmp/dex_response.json)
rm -f /tmp/dex_response.json

DEX_TOKEN=$(echo "${DEX_TOKEN_RESPONSE}" | jq -r '.access_token // .id_token')

if [[ -z "${DEX_TOKEN}" || "${DEX_TOKEN}" == "null" ]]; then
    log_error "Failed to extract token from Dex response"
    log_error "Response: ${DEX_TOKEN_RESPONSE}"
    exit 1
fi

log_info "Dex token obtained successfully"

# Optional: Display Dex token claims for debugging
if [[ "${ACTIONS_STEP_DEBUG:-false}" == "true" ]]; then
    log_info "Dex Token Claims:"
    echo "${DEX_TOKEN}" | cut -d. -f2 | base64 -d 2>/dev/null | jq '.' >&2 || true
fi

# Step 3: Obtain ArgoCD session token using Dex token
log_info "Obtaining ArgoCD session token..."
ARGOCD_SESSION_RESPONSE=$(curl -sSf \
    -X POST \
    "https://${ARGOCD_SERVER}/api/v1/session" \
    -H "Content-Type: application/json" \
    -d "{\"token\": \"${DEX_TOKEN}\"}")

ARGOCD_SESSION_TOKEN=$(echo "${ARGOCD_SESSION_RESPONSE}" | jq -r '.token')

if [[ -z "${ARGOCD_SESSION_TOKEN}" || "${ARGOCD_SESSION_TOKEN}" == "null" ]]; then
    log_error "Failed to obtain ArgoCD session token"
    log_error "Response: ${ARGOCD_SESSION_RESPONSE}"
    exit 1
fi

log_info "ArgoCD session token obtained successfully (expires in 24 hours)"

# Output the token (stdout for capture)
echo "${ARGOCD_SESSION_TOKEN}"
