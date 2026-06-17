#!/bin/bash

set -e

echo "🔧 Setting up Auto Renamer Bot..."

# Step 1 - Create venv
echo "📦 Creating virtual environment..."
cd /root/auto-renamer
python3 -m venv venv

# Step 2 - Install dependencies
echo "📥 Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt
deactivate

# Step 3 - Copy service file
echo "⚙️ Installing systemd service..."
cp /root/auto-renamer/auto-renamer.service /etc/systemd/system/auto-renamer.service

# Step 4 - Reload systemd
echo "🔄 Reloading systemd..."
systemctl daemon-reload

# Step 5 - Enable service
echo "✅ Enabling service..."
systemctl enable auto-renamer

# Step 6 - Start service
echo "🚀 Starting bot..."
systemctl restart auto-renamer

# Step 7 - Show status
echo ""
echo "📊 Bot Status:"
systemctl status auto-renamer --no-pager

echo ""
echo "✅ Setup complete! Auto Renamer Bot is running."
