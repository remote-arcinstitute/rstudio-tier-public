#!/bin/bash
# ─────────────────────────────────────────────
# File: 01_build/init-tier.sh
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }

USER_FILE="${USER_FILE:-/etc/rstudio/users.txt}"
TIER_FILE="${TIER_FILE:-/etc/rstudio/tier_limits.conf}"
STATE_DIR="${STATE_DIR:-/var/lib/rstudio}"
OUT_CRED="${OUT_CRED:-$STATE_DIR/generated_credentials.txt}"
CENTRAL_LIB="${CENTRAL_LIB:-/usr/local/lib/R/site-library}"
MOCK_ROOT="/mockdir"

mkdir -p "$STATE_DIR"
touch "$OUT_CRED"

# ─────────────────────────────────────────────
# Load Tier Limits
# ─────────────────────────────────────────────
declare -A CPU_LIMIT MEM_LIMIT

if [[ -f "$TIER_FILE" ]]; then
  while IFS=':, ' read -r name cpu mem; do
    [[ "$name" =~ ^#|^$ ]] && continue
    CPU_LIMIT[$name]=$cpu
    MEM_LIMIT[$name]=$mem
  done < "$TIER_FILE"
else
  log "Warning: $TIER_FILE not found; using defaults"
  CPU_LIMIT=( ["tier-small"]=1000 ["tier-medium"]=2000 ["tier-large"]=4000 ["tier-admin"]=8000 )
  MEM_LIMIT=( ["tier-small"]=2048 ["tier-medium"]=4096 ["tier-large"]=8192 ["tier-admin"]=16384 )
fi

# ─────────────────────────────────────────────
# User Creation
# ─────────────────────────────────────────────
if [[ -s "$USER_FILE" ]]; then
  log "Loading users from $USER_FILE"
  while IFS=',' read -r username password tier groups home symlink; do
    [[ "$username" =~ ^#|^$ ]] && continue
    log "Creating user: $username (tier=$tier groups=$groups)"
    log "Tier limits: CPU=${CPU_LIMIT[$tier]}m MEM=${MEM_LIMIT[$tier]}Mi"

    mkdir -p "$home"

    # Create groups
    IFS='|' read -ra grp_list <<< "$groups"
    for g in "${grp_list[@]}"; do
      getent group "$g" >/dev/null || groupadd -r "$g"
    done

    main_group=$(echo "$groups" | cut -d'|' -f1)
    if ! id "$username" >/dev/null 2>&1; then
      useradd -m -d "$home" -g "$main_group" -s /bin/bash "$username"
    fi
    echo "$username:$password" | chpasswd

    for g in "${grp_list[@]}"; do
      usermod -aG "$g" "$username"
    done

    # Link shared R library
    ln -sfn "$CENTRAL_LIB" "$home/R"

    # Resolve symlink target (to Project Center)
    if [[ -d "$MOCK_ROOT/Project Center" ]]; then
      target="${MOCK_ROOT}/Project Center/${g}.HealthSystemInstitute"
      if [[ -d "$target" ]]; then
        ln -sfn "$target" "$home/ProjectCenter"
      fi
    fi

    chown -R "$username:$main_group" "$home"
    echo "$username:$password,$tier,$groups" >> "$OUT_CRED"

  done < "$USER_FILE"
else
  log "No $USER_FILE found; skipping user creation"
fi

log "User provisioning complete. Credentials stored at $OUT_CRED"

# ─────────────────────────────────────────────
# Display created users
# ─────────────────────────────────────────────
cat "$OUT_CRED" || true

exec /init
