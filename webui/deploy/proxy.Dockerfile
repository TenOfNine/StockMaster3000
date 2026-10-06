# Reverse Proxy (Caddy) mit gebauter React-SPA. Basis-Images per Digest gepinnt.
ARG REGISTRY=docker.io/library
FROM ${REGISTRY}/node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS bau
RUN npm install --global --ignore-scripts pnpm@10.28.0
WORKDIR /bau
COPY webui/frontend/package.json webui/frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY webui/frontend/ ./
RUN pnpm build

FROM ${REGISTRY}/caddy:2-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f
# Ports über 1024 brauchen keine Datei-Capability; ohne sie startet Caddy auch mit
# cap_drop: ALL und no-new-privileges.
RUN setcap -r /usr/bin/caddy \
 && addgroup -S -g 10002 caddy && adduser -S -u 10002 -G caddy caddy \
 && mkdir -p /data /config && chown -R caddy:caddy /data /config
COPY webui/deploy/Caddyfile /etc/caddy/Caddyfile
COPY webui/deploy/proxy-start.sh /usr/local/bin/proxy-start.sh
RUN chmod 755 /usr/local/bin/proxy-start.sh
COPY --from=bau /bau/dist /srv
USER caddy
EXPOSE 8080 8443
# Das Startskript prüft die Namen aus der Umgebung und startet Caddy.
CMD ["/usr/local/bin/proxy-start.sh"]
