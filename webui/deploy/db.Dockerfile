# PostgreSQL mit eingebautem Init-Skript (Anwendungsrolle ohne Superuser-Rechte), damit der
# Portainer-Stack keine Dateien vom Host einbinden muss. Basis-Image per Digest gepinnt.
ARG REGISTRY=docker.io/library
FROM ${REGISTRY}/postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
COPY webui/deploy/db-init/01-app-rolle.sh /docker-entrypoint-initdb.d/01-app-rolle.sh
COPY webui/deploy/db-abgleich.sh /usr/local/bin/db-abgleich.sh
RUN chmod 0555 /docker-entrypoint-initdb.d/01-app-rolle.sh /usr/local/bin/db-abgleich.sh
# Passwörter bei jedem Start mit den Umgebungsvariablen abgleichen (siehe db-abgleich.sh).
ENTRYPOINT ["db-abgleich.sh"]
CMD ["postgres"]
