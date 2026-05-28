# Cloudflare Tunnel + Zero Trust Setup

This app uses Cloudflare Tunnel so the Mac Mini never needs an open firewall port.
Cloudflare Zero Trust restricts access to `@paceacademy.edu` email addresses.

---

## Prerequisites

- A Cloudflare account (free tier works)
- A domain managed by Cloudflare DNS (e.g. `yourdomain.com`)
- `cloudflared` installed on the Mac Mini: `brew install cloudflare/cloudflare/cloudflared`

---

## Step 1 — Login to Cloudflare

```bash
cloudflared tunnel login
```

This opens a browser. Pick your domain. A cert is saved to `~/.cloudflared/cert.pem`.

---

## Step 2 — Create the tunnel

```bash
cloudflared tunnel create pace-ai-edu
```

Note the tunnel ID printed (looks like `abc123de-...`). You'll use it below.

---

## Step 3 — Create the config file

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: pace-ai-edu
credentials-file: /Users/<your-user>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: pace-ai-edu.yourdomain.com
    service: http://localhost:3001
  - service: http_status:404
```

Replace `<your-user>`, `<tunnel-id>`, and `yourdomain.com` with real values.

---

## Step 4 — Add DNS record

```bash
cloudflared tunnel route dns pace-ai-edu pace-ai-edu.yourdomain.com
```

This creates a CNAME in your Cloudflare DNS automatically.

---

## Step 5 — Get the tunnel token for .env

```bash
cloudflared tunnel token pace-ai-edu
```

Copy the output and paste it as `CLOUDFLARE_TUNNEL_TOKEN` in your `.env` file.

---

## Step 6 — Set up Zero Trust access policy

1. Go to [one.dash.cloudflare.com](https://one.dash.cloudflare.com) → **Access** → **Applications**
2. Click **Add an Application** → **Self-hosted**
3. Name: `Pace AI Edu`
4. Subdomain: `pace-ai-edu`, Domain: `yourdomain.com`
5. Under **Policies**, add a policy:
   - Name: `Pace Academy Staff`
   - Action: **Allow**
   - Include rule: **Emails ending in** → `paceacademy.edu`
6. Save.

Now anyone hitting `pace-ai-edu.yourdomain.com` will be prompted to authenticate with their Pace email. The `Cf-Access-Authenticated-User-Email` header is automatically injected into every request — this is how the app knows who is logged in.

---

## Step 7 — Run as a background service (optional, recommended)

```bash
sudo cloudflared service install
sudo launchctl start com.cloudflare.cloudflared
```

This makes cloudflared start automatically on boot.

---

## Testing

```bash
cloudflared tunnel run pace-ai-edu   # run manually first to verify
```

Visit `https://pace-ai-edu.yourdomain.com` — you should see the Cloudflare Access login page.
