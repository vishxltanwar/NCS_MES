# Production deployment

This deployment runs the MES on one Linux server using Docker Compose:

```
Internet -> Caddy (HTTPS) -> Django/Gunicorn -> PostgreSQL
```

Only Caddy exposes ports `80` and `443`. PostgreSQL and Django remain on the
private Docker network. Caddy obtains and renews the TLS certificate after the
domain DNS points to the server.

## Before starting

1. Use a supported Linux server with Docker Engine and the Docker Compose plugin.
2. Point the DNS A/AAAA record for the MES domain to that server, and allow TCP
   ports 80 and 443 through the firewall.
3. Copy the production template and protect it:

   ```bash
   cp deploy/.env.production.example deploy/.env.production
   chmod 600 deploy/.env.production
   openssl rand -base64 48
   ```

4. Put the generated value in `SECRET_KEY`, choose a unique database password,
   set that same password in both `DB_PASSWORD` and `POSTGRES_PASSWORD`, and
   replace `mes.example.com` in `MES_DOMAIN`, `ALLOWED_HOSTS`, and
   `CSRF_TRUSTED_ORIGINS` with the real DNS name. Keep each `POSTGRES_*` value
   equal to its corresponding `DB_*` value.

## Start and validate

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f web
docker compose exec web python manage.py seed_users
```

Open `https://<your-domain>` and sign in. If `MES_SEED_USERNAME` and
`MES_SEED_PASSWORD` were supplied, remove them from `deploy/.env.production`
after the initial account has been created, then apply the change with:

```bash
docker compose up -d
```

## Operations

```bash
# Back up the database to a host file
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > mes-backup.sql

# Apply a code update
git pull
docker compose up -d --build

# Inspect service logs
docker compose logs --tail=200 web caddy db
```

Store backups outside the server and periodically test restoring one. Do not run
`docker compose down -v` in production: it destroys the database volume.

## Factory hardware

The application container cannot automatically access a Windows COM port or a
Windows network share. Configure these integrations intentionally before launch:

- For a serial scanner on the Linux host, pass the exact device (for example
  `/dev/ttyUSB0`) to the `web` service and set `SCANNER_PORT` accordingly.
- For `LASER_SERIAL_FILE`, mount the approved SMB share on the host, bind-mount
  only that directory into `web`, then use the container path in
  `deploy/.env.production`.
- The magnet insertion PLC defaults to `192.168.3.10` (`PLC_HOST`). The `web`
  container must have a route to the PLC's subnet and firewall permission to
  reach TCP port `502`. This is a routed network/layer-3 concern, not something
  Docker port publishing changes: verify it from inside the container with
  `docker compose exec web python -c "import socket; socket.create_connection(('192.168.3.10', 502), 3)"`.
  If the PLC is only reachable from the machine PC, either put the MES on that
  network or install a route/relay; publishing port `8000` will not fix it.

Use stable device names (for example `/dev/serial/by-id/...`) rather than
`/dev/ttyUSB0` where possible.
