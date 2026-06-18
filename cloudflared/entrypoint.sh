#!/bin/sh
# Starts cloudflared Quick Tunnel, extracts the random URL from logs,
# and POSTs it to a Cloudflare Worker KV so a fixed *.workers.dev URL
# always redirects to the current tunnel.

TUNNEL_TARGET="${TUNNEL_TARGET:-http://frontend:5173}"
WORKER_UPDATE_URL="${WORKER_UPDATE_URL:-}"
LOG_FILE="/tmp/cf.log"

echo "[tunnel] Starting cloudflared -> $TUNNEL_TARGET"

# Run cloudflared in background, capturing all output to file + stdout
cloudflared tunnel --no-autoupdate --url "$TUNNEL_TARGET" >"$LOG_FILE" 2>&1 &
CF_PID=$!

# Also stream logs to container stdout so `docker logs` still works
tail -f "$LOG_FILE" &

# Wait up to 90 seconds for the Quick Tunnel URL to appear in logs
i=0
TUNNEL_URL=""
while [ $i -lt 90 ]; do
  TUNNEL_URL=$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
  i=$((i + 1))
done

if [ -z "$TUNNEL_URL" ]; then
  echo "[tunnel] WARNING: Could not extract tunnel URL after 90s"
else
  echo "[tunnel] Quick Tunnel URL: $TUNNEL_URL"

  if [ -n "$WORKER_UPDATE_URL" ]; then
    echo "[tunnel] Updating Cloudflare Worker KV..."
    RESPONSE=$(curl -sf -X POST "${WORKER_UPDATE_URL}/update" \
      -H "Content-Type: application/json" \
      -d "{\"key\":\"analyzer\",\"value\":\"${TUNNEL_URL}\"}" 2>&1)
    if [ $? -eq 0 ]; then
      echo "[tunnel] Worker KV updated: $RESPONSE"
    else
      echo "[tunnel] WARNING: Failed to update Worker KV: $RESPONSE"
    fi
  else
    echo "[tunnel] WORKER_UPDATE_URL not set - skipping KV update"
  fi
fi

# Wait for cloudflared to exit (keeps container alive)
wait $CF_PID
