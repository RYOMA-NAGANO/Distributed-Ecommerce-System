# Amazon Service Scaffold

This folder is a minimal project scaffold for the Amazon side of the Mini-Amazon / Mini-UPS project.

## Stack

- Django web app
- PostgreSQL
- Separate Python daemon process
- Docker Compose

## Layout

- `amazon_web/`: Django project settings
- `store/`: Django app for models, views, templates, and UPS-facing HTTP endpoints
- `daemon/`: background process for world simulator integration
- `docker/`: Dockerfiles and entrypoint scripts

## Quick Start

1. Copy `.env.example` to `.env`
2. Review the environment variables
3. Run:

```bash
docker compose up --build
```

The web app will be available on port `8000`.
