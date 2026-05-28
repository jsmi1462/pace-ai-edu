# Cloudflare Tunnel Setup

## Quick Tunnel (no domain required — use this for the demo)

Install cloudflared once:
```bash
brew install cloudflare/cloudflare/cloudflared
```

That's it. `start.sh` launches the tunnel automatically and prints a public URL:
```
https://random-words.trycloudflare.com
```

**Notes:**
- URL is public and works immediately — no account, no domain needed
- URL changes every time you restart (fine for a live demo you control)
- Auth uses `DEV_EMAIL` from `.env` — set it to a Pace teacher email so it looks real

---

## Named Tunnel with Custom Domain (permanent URL + Zero Trust email gate)

Use this if you later want a stable URL and to restrict access to `@paceacademy.edu`.

**Prerequisites:** A domain added to Cloudflare DNS (cheapest: ~$1-2/yr `.xyz` from Namecheap).

```bash
cloudflared tunnel login                                          # browser auth
cloudflared tunnel create pace-ai-edu                            # note the tunnel ID
cloudflared tunnel route dns pace-ai-edu pace.yourdomain.com     # add CNAME
cloudflared tunnel token pace-ai-edu                             # copy token
```

Create `~/.cloudflared/config.yml`:
```yaml
tunnel: pace-ai-edu
credentials-file: /Users/<you>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: pace.yourdomain.com
    service: http://localhost:3001
  - service: http_status:404
```

Add to `.env`:
```
CLOUDFLARE_TUNNEL_TOKEN=<token from above>
NODE_ENV=production
```

Update `start.sh` tunnel block to use the named tunnel:
```bash
cloudflared tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN" &
```

**Zero Trust email policy** (Cloudflare dashboard):
1. Access → Applications → Add Self-hosted → `pace.yourdomain.com`
2. Policy: Allow — Emails ending in `@paceacademy.edu`
