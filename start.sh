#!/bin/bash

echo "🌸 Starting AI Girlfriend Bot... 🌸"
echo ""
echo "Make sure you have:"
echo "1. Created a .env file with your API keys"
echo "2. Installed all requirements (pip install -r requirements.txt)"
echo ""
echo "Starting bot..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please create one with your API keys."
    echo "You can copy env_example.txt to .env and edit it."
    exit 1
fi

# Start the bot
python3 bot.py 