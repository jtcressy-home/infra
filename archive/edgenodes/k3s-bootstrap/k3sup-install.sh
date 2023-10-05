# Initial Master Node - ONLY USE WHEN BOOTSTRAPPING CLUSTER
k3sup install \
  --host raspberrypi-4a06138.jtcressy-home.org.github.beta.tailscale.net \
  --user ubuntu \
  --cluster \
  --k3s-channel stable \
  --local-path ~/.kube/config --merge --context=rpik3s \
  --k3s-extra-args '--flannel-iface tailscale0 --flannel-backend host-gw --disable "traefik,local-storage"'

# Master nodes should connect to the previous for initial configuration

k3sup join \
  --host raspberrypi-4a06138.jtcressy-home.org.github.beta.tailscale.net \
  --user ubuntu \
  --server-user ubuntu \
  --server-host raspberrypi-b38e0bf.jtcressy-home.org.github.beta.tailscale.net \
  --server \
  --k3s-channel stable \
  --k3s-extra-args '--flannel-iface tailscale0 --flannel-backend host-gw --disable "traefik,local-storage"'

k3sup join \
  --host raspberrypi-b7162e4.jtcressy-home.org.github.beta.tailscale.net \
  --user ubuntu \
  --server-user ubuntu \
  --server-host raspberrypi-4a06138.jtcressy-home.org.github.beta.tailscale.net \
  --server \
  --k3s-channel stable \
  --k3s-extra-args '--flannel-iface tailscale0 --flannel-backend host-gw --disable "traefik,local-storage"'

k3sup join \
  --host raspberrypi-b38e0bf.jtcressy-home.org.github.beta.tailscale.net \
  --user ubuntu \
  --server-user ubuntu \
  --server-host raspberrypi-b7162e4.jtcressy-home.org.github.beta.tailscale.net \
  --server \
  --k3s-channel stable \
  --k3s-extra-args '--flannel-iface tailscale0 --flannel-backend host-gw --disable "traefik,local-storage"'

# Agent Nodes
k3sup join \
  --host $AGENT_HOSTNAME \
  --user ubuntu \
  --server-user ubuntu \
  --server-host raspberrypi-4a06138.jtcressy-home.org.github.beta.tailscale.net \
  --k3s-channel stable \
  --k3s-extra-args '--flannel-iface tailscale0'


k3sup join \
  --host lenovo-r9dwedy.jtcressy-home.org.github.beta.tailscale.net \
  --user ubuntu \
  --server-user ubuntu \
  --server-host raspberrypi-4a06138.jtcressy-home.org.github.beta.tailscale.net \
  --k3s-channel stable \
  --k3s-extra-args '--flannel-iface tailscale0'