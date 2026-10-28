#!/usr/bin/env bash
# Sets up Dory on a fresh Ubuntu server (tested for Oracle Cloud "Always Free" VMs).
# Run from the repo folder on the server:   bash deploy/setup.sh
# Safe to run again: it only adds what is missing, then rebuilds and restarts Dory.
set -euo pipefail
cd "$(dirname "$0")/.."

# 0. Small servers (Oracle's free E2.1.Micro has 1 GB): add 2 GB of swap so building the
#    website doesn't run out of memory.
if [ "$(free -m | awk '/^Mem:/{print $2}')" -lt 3000 ] && ! swapon --show | grep -q /swapfile; then
  echo "== Adding 2 GB swap"
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# 1. Docker
if ! command -v docker >/dev/null; then
  echo "== Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

# 2. Oracle's Ubuntu images block everything but SSH in the server's own firewall:
#    allow the website (80 = HTTP, 443 = HTTPS). The cloud "security list" must allow them too.
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
  fi
done
if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save >/dev/null; fi

# 3. Settings: .env from the template on first run, plus a free HTTPS name from the server's IP
[ -f .env ] || { cp env.example .env; chmod 600 .env; echo "== Created .env from env.example"; }
if ! grep -q '^DORY_DOMAIN=' .env; then
  ip=$(curl -fsS https://api.ipify.org)
  echo "DORY_DOMAIN=${ip//./-}.sslip.io" >> .env
fi
domain=$(grep '^DORY_DOMAIN=' .env | cut -d= -f2)
grep -q '^DORY_CORS_ORIGINS=' .env || echo "DORY_CORS_ORIGINS=https://${domain}" >> .env
mkdir -p server-data

if grep -q '^NEBIUS_API_KEY=your-' .env; then
  echo "!! Put your Nebius key in .env (NEBIUS_API_KEY=...), then run this script again."
  exit 1
fi

# 4. Start Dory (the bot too if a Telegram token is set)
profiles=""
grep -q '^TELEGRAM_BOT_TOKEN=[0-9]' .env && profiles="--profile bot"
sudo docker compose $profiles up -d --build

echo
echo "== Dory is starting. In a minute:"
echo "   Website:          https://${domain}"
echo "   API (for the app): https://${domain}/api"
echo "   Demo login:       demo@dory.app / the DORY_DEMO_PASSWORD in .env (default dory-demo-2026)"
