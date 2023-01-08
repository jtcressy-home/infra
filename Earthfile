VERSION 0.6

kairos-extension-all-platforms:
  BUILD --platform linux/amd64 +kairos-extension
  BUILD --platform linux/arm64 +kairos-extension

kairos-extension:
  ARG extension
  ARG kairos-version
  FROM DOCKERFILE -f kairos-extensions/${extension}/Dockerfile --build-arg VERSION=${kairos-version} .

  SAVE IMAGE --push ghcr.io/jtcressy-home/infra/kairos-extension-${extension}:${kairos-version}