#!/bin/sh
# Railway et Docker montent le volume /app/data en root : on le donne à l'utilisateur "bot",
# puis on lance le bot avec cet utilisateur (sans les droits root).
set -e
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data
    chown -R bot:bot /app/data
    exec setpriv --reuid=bot --regid=bot --init-groups "$@"
fi
exec "$@"
