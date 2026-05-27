#!/bin/bash
# Source cookies env if it exists
if [ -f /app/cookies/user_cookies.env ]; then
    set -a
    source /app/cookies/user_cookies.env
    set +a
fi
# Source main env if it exists
if [ -f /app/.env ]; then
    set -a
    source /app/.env
    set +a
fi
# Run the main command
exec python main.py