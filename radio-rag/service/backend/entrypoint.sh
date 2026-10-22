#!/bin/sh
# Substitute this instance's API upstream into the served nginx config, then
# hand off to the official nginx entrypoint (which runs nginx).
#
# API_UPSTREAM is the api host:port for THIS instance (radio_api:8003).
set -eu

UPSTREAM="${API_UPSTREAM:-radio_api:8003}"

if [ -f /etc/nginx/templates-api/default.conf.template ]; then
    sed "s#__API_UPSTREAM__#${UPSTREAM}#g" \
        /etc/nginx/templates-api/default.conf.template \
        > /etc/nginx/conf.d/default.conf
elif [ -f /etc/nginx/conf.d/default.conf ] && [ -w /etc/nginx/conf.d/default.conf ]; then
    sed -i "s#__API_UPSTREAM__#${UPSTREAM}#g" /etc/nginx/conf.d/default.conf
else
    echo "entrypoint: no nginx config to configure" >&2
    exit 1
fi

exec /docker-entrypoint.sh "$@"
