# Deployment guide — edge/cloud split, $0 budget

## Why split, not lift-and-shift

`device-management-service` scans a local subnet (`192.168.x.0/24`) and
`data-collector-service` polls real Modbus/FINS PLCs — both need direct
network access to your local LAN, which a cloud VM simply does not have.
Everything else (`ai-agent`, `production`, the frontend, Redis, RabbitMQ)
has no hardware dependency and can live in the cloud.

```
┌─────────────────────── your LAN ───────────────────────┐        ┌──────────────────── cloud VM (free tier) ────────────────────┐
│  PLCs / sensors  ←→  device-management, data-collector   │        │  redis, rabbitmq, ai-agent, production, frontend, Caddy        │
│  timescaledb (local — only data-collector reads it)      │        │                                                                │
└──────────────────────────┬───────────────────────────────┘        └───────────────────────────────┬────────────────────────────────┘
                            └──────────────── Tailscale (private mesh VPN, free) ─────────────────────┘
```

Only Caddy has a public port. Browsers talk to Caddy; Caddy reaches the
edge node's APIs over the private Tailscale link. The PLC-facing services
are never internet-exposed.

The unused local `postgres` container in the original `docker-compose.yml`
is dropped in both new files — every service already talks to Neon directly
(`DATABASE_URL` points at neon.tech), so it was dead weight.

## Cost: $0

| Piece | Where | Cost |
|---|---|---|
| Cloud VM | Oracle Cloud "Always Free" — Ampere A1, up to 4 OCPU / 24GB RAM | Free, no expiry |
| Edge node | Your own machine, or a Pi/mini-PC near the line | Hardware you already have |
| Private network | Tailscale (personal plan) | Free up to 100 devices |
| Relational DB | Neon (already in use) | Free tier |
| TLS | Caddy + Let's Encrypt, or Tailscale Funnel | Free either way |

No Kubernetes here — for one VM and one edge node, Compose is simpler and
has no control-plane cost. Revisit k3s only if you later need multiple
cloud nodes.

## Setup steps

1. **Create the cloud VM.** Sign up for Oracle Cloud, create an Ampere A1
   instance (Ubuntu), install Docker + Compose plugin.

2. **Join both machines to Tailscale.** Install the Tailscale client on
   the cloud VM and on your edge machine, log both into the same tailnet.
   Note their MagicDNS names (Tailscale admin console →
   `<name>.<tailnet>.ts.net`) — these are your `EDGE_HOST` / `CLOUD_HOST`.

3. **Pick a public-access route** — no domain needed:
   - **Simplest ($0, no domain):** leave `PUBLIC_DOMAIN` unset in
     `.env.cloud`, then on the cloud VM run:
     ```
     tailscale funnel 80
     ```
     This gives you a public HTTPS URL (`https://cloud-vm.<tailnet>.ts.net`)
     with a certificate Tailscale manages for you — nothing to configure in Caddy.
   - **If you have a free domain** (e.g. via DuckDNS): point it at the VM's
     public IP, set `PUBLIC_DOMAIN=yourdomain.com` in `.env.cloud`, and
     Caddy issues its own Let's Encrypt certificate automatically.

4. **Configure secrets.** Copy [.env.edge.example](.env.edge.example) →
   `.env.edge` on the edge node, and [.env.cloud.example](.env.cloud.example)
   → `.env.cloud` on the VM. Fill in real values — `RABBITMQ_PASSWORD` must
   match on both sides. Rotate the Anthropic key first if you haven't yet
   (see prior note — it was committed to git history).

5. **Bring the cloud side up** (on the VM):
   ```
   docker compose -f docker-compose.cloud.yml --env-file .env.cloud up -d --build
   ```

6. **Bring the edge side up** (on your LAN machine):
   ```
   docker compose -f docker-compose.edge.yml --env-file .env.edge up -d --build
   ```

7. **Verify the loop end to end**: check `/health` on all four services,
   confirm the frontend loads over the public URL and shows live device
   data, and confirm anomalies still trigger AI decisions in the audit log.

## What deliberately stays out of this deployment

- **Ollama is not installed on the cloud VM.** The free-tier VM's shared
  vCPUs won't give representative local-inference numbers, and paying for
  a GPU instance to keep a model warm isn't a low-budget option. Keep the
  cloud-vs-local comparative benchmark on your own dedicated hardware
  (already measured against llama3.2:3b and qwen2.5:3b) — cleaner
  methodology, and it's honest to state in the write-up that the deployed
  demo uses the cloud LLM path while the local-inference evaluation was
  conducted under controlled conditions on separate hardware.
- **Kubernetes** — not needed for a single VM + single edge node; revisit
  only if the architecture grows to multiple cloud nodes.

## Security checklist before this is ever reachable from the internet

- [ ] Anthropic API key rotated (the old one is still in git history)
- [ ] `RABBITMQ_PASSWORD` / `TIMESCALE_PASSWORD` are real secrets, not `mes123`
- [ ] RabbitMQ management UI (15672), Redis (6379), TimescaleDB (5433) have
      **no public port mapping** — only reachable over the private Tailscale
      interface or from inside the compose network
- [ ] Only Caddy (80/443) is open on the cloud VM's public firewall/security list
- [ ] `device-management` / `data-collector` keep `privileged: true` only on
      the edge node — never on anything internet-facing
