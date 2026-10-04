#!/bin/bash
# Server Setup Script for The Autonomous Alpha on Vultr
if [ "$EUID" -ne 0 ]
  then echo "Please run as root"
  exit
fi

echo "🚀 Setting up The Autonomous Alpha environment..."

# Update system
echo "📦 Updating system packages..."
apt-get update && apt-get upgrade -y
apt-get install -y curl git ufw

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "🐙 Installing Docker Compose..."
    LATEST_COMPOSE=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep "tag_name" | cut -d '"' -f 4)
    curl -L "https://github.com/docker/compose/releases/download/${LATEST_COMPOSE}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    echo "✅ Docker Compose already installed"
fi

# Configure Firewall
echo "🛡️ Configuring Firewall..."
ufw allow 22/tcp    # SSH
ufw allow 5000/tcp  # Dashboard
ufw allow 3000/tcp  # Grafana
# ufw enable  # Uncomment to enable immediately (careful not to lock yourself out!)

echo "✅ Setup complete! run 'docker-compose up -d' to start."
