FROM alpine as build
ARG VERSION
ENV VERSION=$VERSION

RUN apk add curl jq tree

RUN tarball="$(curl 'https://pkgs.tailscale.com/stable/?mode=json' | jq -r .Tarballs.amd64)" && \
    version="$(echo ${tarball} | cut -d_ -f2)" && \
    curl "https://pkgs.tailscale.com/stable/${tarball}" -o tailscale.tgz && \
    mkdir -p \
        /tailscale/usr/bin \
        /tailscale/usr/sbin \
        /tailscale/usr/lib/systemd/system \
        /tailscale/usr/lib/extension-release.d && \
    tar xzf tailscale.tgz && \
    cp -vrf "tailscale_${version}_amd64"/tailscale /tailscale/usr/bin/tailscale && \
    cp -vrf "tailscale_${version}_amd64"/tailscaled /tailscale/usr/sbin/tailscaled && \
    cp -vrf "tailscale_${version}_amd64"/systemd/tailscaled.service /tailscale/usr/lib/systemd/system/tailscaled.service && \
    sed -i 's/--port.*//g' /tailscale/usr/lib/systemd/system/tailscaled.service

RUN echo ID=kairos > /tailscale/usr/lib/extension-release.d/extension-release.tailscale && \
    echo VERSION_ID=$VERSION >> /tailscale/usr/lib/extension-release.d/extension-release.tailscale

FROM scratch

COPY --from=build /tailscale/usr/bin/tailscale /usr/bin/tailscale
COPY --from=build /tailscale/usr/sbin/tailscaled /usr/sbin/tailscaled
COPY --from=build /tailscale/usr/lib/extension-release.d /usr/lib/extension-release.d
COPY --from=build /tailscale/usr/lib/systemd/system/tailscaled.service /usr/lib/systemd/system/tailscaled.service
