VERSION 0.6

kairos-extension:
  ARG extension
  ARG kairos-version
  FROM DOCKERFILE -f kairos-extensions/${extension}/Dockerfile --build-arg VERSION=${kairos-version} .

  SAVE IMAGE --push ghcr.io/jtcressy-home/infra/kairos-extension-${extension}:${kairos-version}