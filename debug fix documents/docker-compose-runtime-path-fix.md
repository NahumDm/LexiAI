# Docker Compose Runtime Path Fix

## Problem
`docker-compose up` was starting the Django and Celery containers from `/app`, but the project files are mounted under `/app/lexiai_backend`.

That caused:
- `python: can't open file '/app/manage.py'`
- Celery failing to import the app module because the package root was wrong

## Fix
Updated `lexiai_backend/docker-compose.yml` to set:
- `working_dir: /app/lexiai_backend` for `web`
- `working_dir: /app/lexiai_backend` for `worker`
- `working_dir: /app/lexiai_backend` for `beat`

## Result
The containers now start from the directory that actually contains `manage.py` and the inner `lexiai_backend` package, so Django and Celery resolve correctly.

## Notes
If Docker Desktop is not fully running, `docker-compose up` can still fail before the containers start. The fix here addresses the project path issue inside the containers.
