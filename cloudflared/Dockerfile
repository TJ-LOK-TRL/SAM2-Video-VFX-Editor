FROM cloudflare/cloudflared:latest AS cf
FROM alpine:3.19
RUN apk add --no-cache curl
COPY --from=cf /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
