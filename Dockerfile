# docker-compose.yml
version: "3.9"

services:
  db:
    image: postgres:15
    container_name: detecktiv_db
    environment:
      POSTGRES_DB: detecktiv
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB -h 127.0.0.1"]
      interval: 5s
      timeout: 3s
      retries: 20
    restart: unless-stopped

  # Optional dev SMTP server (Mailpit). Web UI at http://localhost:8025
  mail:
    image: axllent/mailpit:latest
    container_name: detecktiv_mail
    ports:
      - "1025:1025"   # SMTP
      - "8025:8025"   # Web UI
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: detecktiv_api
    env_file:
      - .env
    environment:
      # DB — set DATABASE_URL explicitly so SQLAlchemy uses the right driver & schema
      DATABASE_URL: "postgresql+psycopg2://postgres:postgres@db:5432/detecktiv?sslmode=disable&options=-csearch_path%3Dapp"
      POSTGRES_SCHEMA: "app"

      # JWT / Auth defaults (override in .env for real secrets)
      SECRET_KEY: "change-me"
      JWT_ALG: "HS256"
      ACCESS_TOKEN_EXPIRES_SECONDS: "900"
      REFRESH_TOKEN_EXPIRES_SECONDS: "1209600"

      # CORS (adjust to your frontend origin)
      CORS_ORIGINS: "http://localhost:5173"

      # Optional cookies
      AUTH_COOKIES: "0"

      # Optional rate limits
      RATE_LIMIT_ENABLED: "1"
      RATE_LIMIT_AUTH_LOGIN: "10/minute"
      RATE_LIMIT_AUTH_REFRESH: "60/minute"

      # Mail (points to the dev SMTP container above)
      SMTP_HOST: "mail"
      SMTP_PORT: "1025"
      MAIL_FROM: "no-reply@local.test"
      MAIL_FROM_NAME: "detecktiv.io"

      # OpenAPI servers (so the docs try the right host)
      OPENAPI_SERVERS: "http://localhost:8000"
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
