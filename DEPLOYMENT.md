# Deploying to Vultr VPS

This guide walks you through deploying The Autonomous Alpha on a Vultr VPS.

## Prerequisites

- A Vultr Account
- A VPS Instance (Cloud Compute or High Frequency)
  - **OS:** Ubuntu 22.04 LTS or newer
  - **Plan:** Minimum $12-24/mo (4GB RAM, 2 vCPUs recommended)
  - **Location:** Closest to your exchange (e.g., Tokyo for Binance)

## Step 1: Prepare the Server

1. SSH into your VPS:
   ```bash
   ssh root@your_vps_ip
   ```

2. Upload your code to the VPS:
   
   **Option A: Automatic Upload (Recommended for Windows)**
   Double-click `upload_to_vps.bat` and enter your VPS IP when prompted.
   
   **Option B: Git**
   if you have a git repository:
   ```bash
   git clone https://github.com/your-repo/autonomous-alpha.git
   cd autonomous-alpha
   ```

   **Option C: Manual SFTP**
   Use FileZilla or WinSCP to upload all files to `/root/autonomous-alpha/`.

3. Run the setup script:
   ```bash
   cd autonomous-alpha
   chmod +x setup.sh
   ./setup.sh
   ```

## Step 2: Configure Environment

Create a `.env` file with your secrets:
```bash
nano .env
```

Paste your configuration:
```bash
# Exchange API
BINANCE_API_KEY=your_binance_key
BINANCE_API_SECRET=your_binance_secret

# Trading Mode
TRADING_MODE=paper  # Start with paper!

# Dashboard (Optional)
GRAFANA_PASSWORD=secure_password
```

> **Note:** LLM connection details are already baked into `docker-compose.yml` but can be overridden here if needed.

## Step 3: Launch

Start the agent in the background:
```bash
docker-compose up -d
```

View logs to ensure startup:
```bash
docker-compose logs -f trading-agent
```

## Step 4: Access Dashboard

Open your browser and navigate to:
`http://your_vps_ip:5000`

## Maintenance

- **Stop:** `docker-compose down`
- **Update:** `git pull && docker-compose build && docker-compose up -d`
- **Restart:** `docker-compose restart trading-agent`
