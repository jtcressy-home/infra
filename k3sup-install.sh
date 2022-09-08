export K3S_VERSION=v1.24.4+k3s1
export USER=ubuntu

k3sup install \
  --host raspberrypi-4a06138 \
  --user $USER \
  --cluster \
  --k3s-version $K3S_VERSION

export SERVER_IP=192.168.0.100
export NEXT_SERVER_IP=192.168.0.101

k3sup join \
  --host raspberrypi-b38e0bf \
  --user $USER \
  --server-user $USER \
  --server-host raspberrypi-4a06138 \
  --server \
  --k3s-version $K3S_VERSION

k3sup join \
  --host raspberrypi-b7162e4 \
  --user $USER \
  --server-user $USER \
  --server-host raspberrypi-4a06138 \
  --server \
  --k3s-version $K3S_VERSION

