# Deploying Mailforge Health Dashboard on Vercel for Free

This guide walks you through deploying this dashboard to Vercel using Vercel's free serverless tier.

## Architecture Adjustments for Vercel Serverless
Because Vercel runs on stateless serverless functions:
1. **Database**: Local SQLite databases (`.db` files) will reset on every API call. You must use a persistent remote SQL database. We recommend a free **Neon PostgreSQL** database.
2. **Background Jobs**: Persistent background schedulers like `APScheduler` cannot run continuously on Vercel. Instead, we configure a **Vercel Cron Job** in `vercel.json` to trigger the scan endpoint automatically.

---

## Step 1: Create a Free PostgreSQL Database
1. Go to [Neon.tech](https://neon.tech/) and sign up for a free account.
2. Create a new project/database.
3. Copy your database connection string, which will look like this:
   `postgresql://alex:password@ep-cool-water-123456.us-east-2.aws.neon.tech/neondb?sslmode=require`

---

## Step 2: Deploy to Vercel
1. Install the Vercel CLI or connect your GitHub repository to your Vercel Account.
2. If using Vercel CLI, run:
   ```bash
   vercel
   ```
3. Add the following **Environment Variables** in your Vercel project settings:
   - `MAILFORGE_API_KEY`: Your private Mailforge API key.
   - `OPENROUTER_API_KEY`: (Optional) Your OpenRouter API key.
   - `OPENROUTER_MODEL`: (Optional) `meta-llama/llama-3.1-8b-instruct:free`
   - `DATABASE_URL`: Replace `postgresql://` with `postgresql+psycopg2://` in your Neon Connection String.
     Example:
     `postgresql+psycopg2://alex:password@ep-cool-water-123456.us-east-2.aws.neon.tech/neondb?sslmode=require`

---

## Step 3: Verify the Vercel Cron Job
Inside `vercel.json` we have configured a cron job to automatically trigger the full infrastructure scan daily:
```json
"crons": [
  {
    "path": "/api/scan/full",
    "schedule": "0 0 * * *"
  }
]
```
Ensure you enable cron execution inside your Vercel project's settings dashboard once deployed.
