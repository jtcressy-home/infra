VERSION 0.6

kairos-extension-all-platforms:
  BUILD --platform linux/amd64 +kairos-extension
  BUILD --platform linux/arm64 +kairos-extension

alpine:
  FROM alpine:latest
  SAVE ARTIFACT /bin/sh

version:
  FROM alpine
  ARG EXTENSION
  COPY ./kairos-extensions/${EXTENSION}+version/extension.version /extension.version
  SAVE ARTIFACT /extension.version

kairos-extension:
  FROM alpine
  ARG EXTENSION
  COPY (+version/extension.version --EXTENSION=$EXTENSION) /extension.version
  ARG EXT_VERSION=$(cat /extension.version)
  ARG KAIROS_VERSION
  FROM ./kairos-extensions/${EXTENSION}+extension --KAIROS_VERSION=$KAIROS_VERSION
  SAVE IMAGE --push ghcr.io/jtcressy-home/infra/kairos-extension-${EXTENSION}:${EXT_VERSION}-kairos${KAIROS_VERSION}