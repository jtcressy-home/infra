VERSION 0.6

kairos-extension-all-platforms:
  BUILD --platform linux/amd64 +kairos-extension
  BUILD --platform linux/arm64 +kairos-extension

kairos-extension:
  ARG EXTENSION
  ARG KAIROS_VERSION
  FROM DOCKERFILE -f kairos-extensions/${EXTENSION}/Dockerfile --build-arg VERSION=${KAIROS_VERSION} .

  SAVE IMAGE --push ghcr.io/jtcressy-home/infra/kairos-extension-${EXTENSION}:${KAIROS_VERSION}