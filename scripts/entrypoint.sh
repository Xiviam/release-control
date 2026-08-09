#!/bin/sh
set -eu

alembic upgrade head
python -m app.cli bootstrap-admin
exec "$@"

