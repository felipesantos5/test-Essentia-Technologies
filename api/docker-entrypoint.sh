#!/bin/sh
set -eu

alembic upgrade head
python -m clinic_api.seed
exec uvicorn clinic_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers
