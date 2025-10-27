# Podman Socket Notes (Custom TCP Setup for Multi-Node / K3s)

🔧 Quick Fixes

If curl to the Podman socket fails, first determine which socket you’re using:
```bash
✅ Test User Socket (rootless)
curl --unix-socket /run/user/$(id -u)/podman/podman.sock http://d/v4.0.0/libpod/_ping
```
Expected output:

OK

If it fails, start the socket:
```bash
systemctl --user enable --now podman.socket
🔐 Test System Socket (root)
sudo curl --unix-socket /run/podman/podman.sock http://localhost/v4.0.0/libpod/_ping
```
Expected output:

OK

If this works but the user socket fails, you’re connecting to the wrong one. The user socket is /run/user/<uid>/podman/podman.sock, while the system socket is /run/podman/podman.sock.


## Overview

For distributed deployments (e.g., K3s clusters) where the backend (`rpod-api`) needs to control containers on remote nodes, it's best to use the **Podman REST API over TCP with TLS**. This avoids embedding `podman` CLI binaries inside containers and allows secure, remote orchestration.

---

## 1. Enable Podman Service on Custom Port (8181)

Run this as the target user (e.g., `arcinstitute`) on each node:

```bash
systemctl --user enable --now podman.socket
```

Then stop the default socket and replace it with a custom TCP listener:

```bash
systemctl --user stop podman.socket
podman system service --time=0 \
  --log-level=info \
  tcp:0.0.0.0:8181 \
  --tlsverify \
  --tlscacert /etc/podman/ca.pem \
  --tlscert /etc/podman/server-cert.pem \
  --tlskey /etc/podman/server-key.pem
```

This starts the Podman API service on port **8181**, requiring TLS verification.

---

## 2. Generate TLS Certificates

To generate your own CA and certs (for testing or internal use):

```bash
mkdir -p /etc/podman
cd /etc/podman

# 1. Generate CA key and cert
openssl genrsa -out ca-key.pem 4096
openssl req -x509 -new -nodes -key ca-key.pem -days 3650 -out ca.pem -subj "/CN=Podman-CA"

# 2. Generate server key and cert
openssl genrsa -out server-key.pem 4096
openssl req -new -key server-key.pem -out server.csr -subj "/CN=$(hostname)"
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out server-cert.pem -days 3650

# 3. Generate client key and cert
openssl genrsa -out client-key.pem 4096
openssl req -new -key client-key.pem -out client.csr -subj "/CN=rpod-api"
openssl x509 -req -in client.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial -out client-cert.pem -days 3650

chmod 600 *.pem
```

Distribute the `ca.pem`, `client-cert.pem`, and `client-key.pem` files securely to your backend node.

---

## 3. Firewall and Network Restriction

If using **Tailscale** or a private network, restrict traffic:

```bash
sudo ufw allow from 100.65.0.0/16 to any port 8181 proto tcp
sudo ufw deny 8181
```

Only nodes in your ARC tailnet will be able to access the Podman API.

---

## 4. Configure Backend (rpod-api)

In your backend container or deployment, set:

```bash
export PODMAN_URL=https://100.65.42.6:8181
export PODMAN_CACERT=/etc/podman/ca.pem
export PODMAN_CERT=/etc/podman/client-cert.pem
export PODMAN_KEY=/etc/podman/client-key.pem
```

In Python (using `requests`):

```python
import requests

url = f"{os.getenv('PODMAN_URL')}/v4.0.0/libpod/info"
response = requests.get(
    url,
    cert=(os.getenv('PODMAN_CERT'), os.getenv('PODMAN_KEY')),
    verify=os.getenv('PODMAN_CACERT')
)
print(response.json())
```

---

## 5. Systemd User Service (Optional)

To persist Podman API listener on port 8181:

```bash
mkdir -p ~/.config/systemd/user/podman.service.d
cat <<'EOF' > ~/.config/systemd/user/podman.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/podman system service --time=0 --log-level=info \
  tcp:0.0.0.0:8181 \
  --tlsverify \
  --tlscacert /etc/podman/ca.pem \
  --tlscert /etc/podman/server-cert.pem \
  --tlskey /etc/podman/server-key.pem
EOF

systemctl --user daemon-reload
systemctl --user restart podman.service
systemctl --user enable podman.service
```

This ensures the service starts automatically after reboot.

---

## 6. Test API Connection

From the backend node:

```bash
curl --cacert /etc/podman/ca.pem \
     --cert /etc/podman/client-cert.pem \
     --key /etc/podman/client-key.pem \
     https://100.65.42.6:8181/v4.0.0/libpod/_ping
```

Expected output:

```
OK
```

---

### ✅ Summary

* Use port **8181** (custom Podman service)
* TLS-enabled API ensures secure cross-node access
* `rpod-api` connects via `PODMAN_URL` + TLS certs
* Recommended for multi-node or K3s orchestrations
