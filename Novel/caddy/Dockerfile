FROM alpine:3.21

ARG CADDY_VERSION=2.11.4
ARG TARGETARCH

RUN apk add --no-cache ca-certificates wget \
    && addgroup -S -g 1000 caddy \
    && adduser -S -D -H -u 1000 -G caddy caddy \
    && mkdir -p /etc/caddy /data /config \
    && caddy_asset="caddy_${CADDY_VERSION}_linux_${TARGETARCH}.tar.gz" \
    && wget -qO "/tmp/${caddy_asset}" "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/${caddy_asset}" \
    && wget -qO /tmp/caddy_checksums.txt "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_checksums.txt" \
    && cd /tmp \
    && grep "${caddy_asset}$" caddy_checksums.txt | sha512sum -c - \
    && tar -xzf "/tmp/${caddy_asset}" -C /tmp caddy \
    && cp /tmp/caddy /usr/bin/caddy \
    && chmod 0755 /usr/bin/caddy \
    && rm -f "/tmp/${caddy_asset}" /tmp/caddy_checksums.txt /tmp/caddy \
    && chown -R caddy:caddy /etc/caddy /data /config

COPY Caddyfile /etc/caddy/Caddyfile
RUN chown caddy:caddy /etc/caddy/Caddyfile

USER 1000:1000
EXPOSE 8080

ENTRYPOINT ["caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
