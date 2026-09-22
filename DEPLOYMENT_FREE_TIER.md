# RepoLens Free Tier Deployment Guide

Deploy RepoLens for **$0/month** using free tiers from multiple providers.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Netlify      │     │     Render      │     │   Neo4j Aura    │
│   (Frontend)    │────▶│   (Backend)     │────▶│   (Database)    │
│      FREE       │     │     FREE        │     │      FREE       │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    Upstash      │
                        │    (Redis)      │
                        │      FREE       │
                        └─────────────────┘
```

## Free Tier Limits

| Service | Limit | Sufficient For |
|---------|-------|----------------|
| **Neo4j Aura** | 200K nodes, 400K relationships | ~50 medium repos |
| **Upstash Redis** | 256MB, 500K commands/mo | Normal usage |
| **Render** | 750 hours/mo, spins down after 15min | 1 always-on service with keepalive |
| **Netlify** | 100GB bandwidth/mo | Plenty for SPA |

---

## Step 1: Set Up Neo4j Aura Free

1. Go to https://console.neo4j.io
2. Sign up / Log in
3. Click **"New Instance"** → Select **"AuraDB Free"**
4. Choose a region (pick closest to your Render region)
5. Wait for instance to be ready (~2 minutes)
6. **Save these credentials:**
   ```
   Connection URI: neo4j+s://xxxxxxxx.databases.neo4j.io
   Username: neo4j
   Password: (generated password - SAVE THIS!)
   ```

⚠️ **Important:** The password is only shown once. Save it immediately!

---

## Step 2: Set Up Upstash Redis Free

1. Go to https://console.upstash.com
2. Sign up / Log in
3. Click **"Create Database"**
4. Configure:
   - **Name:** repolens-redis
   - **Region:** Choose same region as Render (e.g., us-east-1)
   - **TLS:** Enabled (required)
5. **Save the connection string:**
   ```
   REDIS_URL: rediss://default:xxxxx@xxxxx.upstash.io:6379
   ```

---

## Step 3: Create GitHub OAuth App

1. Go to https://github.com/settings/developers
2. Click **"New OAuth App"**
3. Fill in:
   - **Application name:** RepoLens
   - **Homepage URL:** `https://your-app.netlify.app` (update after Netlify deploy)
   - **Authorization callback URL:** `https://your-app.onrender.com/api/auth/github/callback`
4. Click **"Register application"**
5. **Save:**
   ```
   Client ID: Ov23li...
   Client Secret: (click "Generate a new client secret")
   ```

⚠️ You'll update the URLs after deploying to get the actual domains.

---

## Step 4: Deploy Backend to Render

### 4.1 Create Render Account
1. Go to https://render.com
2. Sign up with GitHub (recommended for easy repo connection)

### 4.2 Create Web Service
1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repo
3. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `repolens-api` |
| **Region** | Oregon (US West) or closest to you |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `chmod +x start.sh && ./start.sh` |
| **Instance Type** | `Free` |

### 4.3 Add Environment Variables

In Render dashboard → Environment → Add the following:

```env
# App Settings
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# Neo4j Aura (from Step 1)
NEO4J_URI=neo4j+s://YOUR_AURA_ID.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password

# Upstash Redis (from Step 2)
REDIS_URL=rediss://default:your-password@your-endpoint.upstash.io:6379

# GitHub OAuth (from Step 3)
GITHUB_CLIENT_ID=your-client-id
GITHUB_CLIENT_SECRET=your-client-secret
GITHUB_REDIRECT_URI=https://repolens-api.onrender.com/api/auth/github/callback

# Frontend URL (update after Netlify deploy)
FRONTEND_URL=https://your-app.netlify.app

# Security Keys (generate with: openssl rand -hex 32)
JWT_SECRET_KEY=generate-a-random-32-byte-hex-string
SECRET_KEY=generate-another-random-32-byte-hex-string

# LLM Provider
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=xiaomi/mimo-v2-flash

# CORS (update after Netlify deploy)
CORS_ORIGINS=https://your-app.netlify.app

# Performance (optimized for free tier)
UVICORN_WORKERS=1
NEO4J_MAX_CONNECTION_POOL_SIZE=10
REDIS_MAX_CONNECTIONS=10

# Cache directories
HF_HOME=/tmp/huggingface
TORCH_HOME=/tmp/torch

# SSL
SSL_VERIFY=true
FORCE_HTTPS=true
SECURE_COOKIES=true
```

### 4.4 Deploy
Click **"Create Web Service"** and wait for deployment (~5-10 minutes first time).

Your backend URL will be: `https://repolens-api.onrender.com`

---

## Step 5: Deploy Frontend to Netlify

### 5.1 Create Netlify Account
1. Go to https://netlify.com
2. Sign up with GitHub

### 5.2 Deploy from GitHub
1. Click **"Add new site"** → **"Import an existing project"**
2. Connect GitHub and select your repo
3. Configure:

| Setting | Value |
|---------|-------|
| **Branch** | `main` |
| **Build command** | `npm run build` |
| **Publish directory** | `dist` |

### 5.3 Add Environment Variables

In Netlify dashboard → Site settings → Environment variables:

```env
VITE_API_URL=https://repolens-api.onrender.com
VITE_GITHUB_CLIENT_ID=your-github-client-id
```

### 5.4 Deploy
Click **"Deploy site"**

Your frontend URL will be: `https://random-name.netlify.app`

---

## Step 6: Update URLs

Now that you have actual URLs, update them everywhere:

### 6.1 Update Render Environment Variables
- `FRONTEND_URL=https://your-actual-app.netlify.app`
- `CORS_ORIGINS=https://your-actual-app.netlify.app`

### 6.2 Update GitHub OAuth App
1. Go to https://github.com/settings/developers
2. Edit your OAuth app
3. Update:
   - **Homepage URL:** `https://your-actual-app.netlify.app`
   - **Authorization callback URL:** `https://repolens-api.onrender.com/api/auth/github/callback`

### 6.3 Redeploy Render
Trigger a manual deploy in Render dashboard to apply the new environment variables.

---

## Step 7: Set Up Keepalive (Prevent Cold Starts)

Render free tier spins down after 15 minutes of inactivity. Set up a free cron to keep it warm:

### Option A: UptimeRobot (Recommended)
1. Go to https://uptimerobot.com
2. Sign up (free)
3. Click **"Add New Monitor"**
4. Configure:
   - **Monitor Type:** HTTP(s)
   - **Friendly Name:** RepoLens API
   - **URL:** `https://repolens-api.onrender.com/health`
   - **Monitoring Interval:** 5 minutes
5. Save

### Option B: Cron-job.org
1. Go to https://cron-job.org
2. Sign up (free)
3. Create a cron job to hit `https://repolens-api.onrender.com/health` every 14 minutes

---

## Step 8: Verify Deployment

### 8.1 Check Backend Health
```bash
curl https://repolens-api.onrender.com/health
# Should return: {"status": "healthy"}

curl https://repolens-api.onrender.com/health/detailed
# Should show all services connected
```

### 8.2 Test Frontend
1. Visit your Netlify URL
2. Click "Login with GitHub"
3. Authorize the app
4. Try parsing a small repository

---

## Troubleshooting

### "Connection refused" to Neo4j
- Verify you're using `neo4j+s://` (not `bolt://`)
- Check password is correct
- Ensure Aura instance is running (check console.neo4j.io)

### "Connection refused" to Redis
- Verify you're using `rediss://` (not `redis://`)
- Check the full connection string from Upstash dashboard
- Ensure TLS is enabled

### OAuth redirect fails
- Verify `GITHUB_REDIRECT_URI` matches exactly what's in GitHub OAuth app settings
- Verify `FRONTEND_URL` is set correctly
- Check browser console for CORS errors

### Cold starts (30-50 second delays)
- This is normal for Render free tier
- Set up the keepalive cron (Step 7)
- First request after sleep will be slow

### Out of memory errors
- Reduce `NEO4J_MAX_CONNECTION_POOL_SIZE` to 5
- Reduce `REDIS_MAX_CONNECTIONS` to 5
- Disable embeddings: `ENABLE_EMBEDDINGS_ON_PARSE=false`

---

## Cost Monitoring

Check your usage regularly to stay within free limits:

| Service | Where to Check |
|---------|----------------|
| **Neo4j Aura** | https://console.neo4j.io → Instance → Metrics |
| **Upstash** | https://console.upstash.com → Database → Usage |
| **Render** | https://dashboard.render.com → Usage |
| **Netlify** | https://app.netlify.com → Site → Analytics |

---

## Upgrading Later

If you outgrow free tiers:

| Issue | Solution | Cost |
|-------|----------|------|
| Cold starts annoying | Render Starter | $7/mo |
| Need more Redis | Upstash Pay-as-go | ~$1-5/mo |
| Need more Neo4j | Aura Pro or self-host | $65/mo+ |

---

## Quick Reference

After deployment, your URLs will be:

- **Frontend:** `https://your-app.netlify.app`
- **Backend:** `https://repolens-api.onrender.com`
- **Health Check:** `https://repolens-api.onrender.com/health`
- **API Docs:** Disabled in production for security
