# 🚀 LogiTrack Deployment Guide

This guide explains how to deploy the **LogiTrack Logistics Management System** to **Render**, **Railway**, or using **Docker**.

---

## 🔑 Default Seed Credentials (Pre-populated)

When deployed on any platform, LogiTrack automatically initializes the database and creates default user accounts on first launch:

| Role | Username | Password | Notes |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | Full system administrator panel access |
| **Branch Manager** | `manager_bom` | `manager123` | Mumbai Main Hub branch manager |
| **Driver** | `driver_rajesh` | `driver123` | Driver portal for deliveries & pickups |
| **Driver 2** | `driver_amit` | `driver123` | Delhi branch driver |
| **Customer** | `customer_rahul` | `customer123` | Customer booking and tracking dashboard |

---

## 🌐 Option 1: Deploy on Render (Recommended - Free & Easy)

### Step 1: Push Code to GitHub
1. Create a new repository on [GitHub](https://github.com/new) (e.g. `logitrack-deploy`).
2. Run the following commands in your project terminal:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for deployment"
   git branch -M main
   git remote add origin https://github.com/<your-username>/logitrack-deploy.git
   git push -u origin main
   ```

### Step 2: Deploy on Render
1. Log in to [Render.com](https://render.com/).
2. Click **New +** → **Web Service**.
3. Connect your GitHub repository (`logitrack-deploy`).
4. Configure the service settings:
   - **Name**: `logitrack-app` (or your preferred name)
   - **Region**: Nearest to your users (e.g., Singapore, Frankfurt, Oregon)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app`
   - **Instance Type**: `Free`
5. Under **Environment Variables**, add:
   - `FLASK_CONFIG` = `production`
   - `SECRET_KEY` = *(Click Generate or enter a random secure string)*
   - `PYTHON_VERSION` = `3.11.9`
6. *(Optional)* If you create a Render PostgreSQL database, copy its **Internal Database URL** and add:
   - `DATABASE_URL` = `<your-postgres-url>`
7. Click **Create Web Service**. Render will build and deploy your project automatically!

---

## 🚆 Option 2: Deploy on Railway (1-Click Deployment)

1. Log in to [Railway.app](https://railway.app/).
2. Click **New Project** → **Deploy from GitHub repo**.
3. Select your `logitrack-deploy` repository.
4. Railway will automatically detect the `Procfile` / `Dockerfile` and build the service.
5. In your project settings, add variables:
   - `FLASK_CONFIG`: `production`
   - `SECRET_KEY`: *(random secure string)*
6. Under **Settings** → **Networking**, click **Generate Domain** to get your public live URL (e.g. `logitrack.up.railway.app`).

---

## 🐳 Option 3: Deploy with Docker / Docker Compose

### Run locally or on any VPS (AWS, DigitalOcean, Hetzner, Linode):
1. Build and run container:
   ```bash
   docker compose up -d --build
   ```
2. Open your browser at `http://localhost:5000` (or `http://your-server-ip:5000`).

---

## 🛠️ Environment Variables Summary

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `FLASK_CONFIG` | No | `production` | Configuration mode (`production`, `development`, `testing`) |
| `SECRET_KEY` | Recommended | Built-in fallback | Session security key |
| `DATABASE_URL` | No | Local SQLite (`logitrack.db`) | PostgreSQL or MySQL connection string |
| `PORT` | Auto | `5000` | Port assigned by host |
