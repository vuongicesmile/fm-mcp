#!/usr/bin/env sh
# Chỉ chạy migration của fm-mcp trên development hoặc test database.
set -eu

case "${FM_ENV:-development}" in
  development|test) ;;
  *)
    echo "Refusing to run fm-mcp migrations outside FM_ENV=development|test." >&2
    exit 2
    ;;
esac

: "${DATABASE_URL:?DATABASE_URL must point to an isolated development or test database}"
exec alembic -c alembic.ini upgrade head
