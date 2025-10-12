#!/usr/bin/env sh

set -ex

if [ ! -d "/app/node_modules" ]; then
  cp -r /.npm/node_modules/. /app/node_modules/
fi

exec npm run start
