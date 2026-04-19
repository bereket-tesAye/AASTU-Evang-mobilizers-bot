#!/bin/sh
# Entrypoint for AASTU Telegram Bot
# Starts the health server and Telegram bot as detached background processes
set -e

echo "Starting health server..."
setsid python health_server.py &
HEALTH_PID=$!

echo "Starting Telegram bot..."
setsid python evangtelegrambot.py &
BOT_PID=$!

echo "Bot running with PID $BOT_PID, Health server with PID $HEALTH_PID"

# Wait for both processes
wait $HEALTH_PID
wait $BOT_PID
