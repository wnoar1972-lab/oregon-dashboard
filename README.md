# 🏊 IM 70.3 Oregon — Auto Dashboard

Your training dashboard — auto-updated daily from Garmin Connect via GitHub Actions.

---

## ⚡ One-Time Setup (15 minutes)

### Step 1 — Create a GitHub Account
Go to [github.com](https://github.com) and sign up for a free account if you don't have one.

### Step 2 — Create a New Repository
1. Click the **+** button in the top right → **New repository**
2. Name it: `oregon-dashboard`
3. Set it to **Public** (required for free GitHub Pages hosting)
4. Click **Create repository**

### Step 3 — Upload These Files
In your new repository, upload all files from this folder maintaining the structure:
```
oregon-dashboard/
├── index.html
├── requirements.txt
├── .github/
│   └── workflows/
│       └── update.yml
├── scripts/
│   └── fetch_garmin.py
└── data/           ← will be created automatically
```

**Easiest way to upload:**
1. In your repository, click **Add file** → **Upload files**
2. Drag all files in — GitHub will create the folder structure
3. Click **Commit changes**

### Step 4 — Add Your Garmin Credentials (Securely)
1. In your repository, click **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add two secrets:
   - Name: `GARMIN_EMAIL` · Value: your Garmin Connect email
   - Name: `GARMIN_PASSWORD` · Value: your Garmin Connect password
4. These are encrypted — GitHub never shows them again

### Step 5 — Enable GitHub Pages
1. In your repository, click **Settings** → **Pages**
2. Under **Source**, select **Deploy from a branch**
3. Branch: **main** · Folder: **/ (root)**
4. Click **Save**
5. After ~2 minutes, your dashboard will be live at:
   `https://YOUR-GITHUB-USERNAME.github.io/oregon-dashboard/`

### Step 6 — Run Your First Update
1. Go to **Actions** tab in your repository
2. Click **Update Dashboard Daily**
3. Click **Run workflow** → **Run workflow**
4. Wait ~2 minutes for it to complete
5. Refresh your GitHub Pages URL — dashboard is live with real data!

---

## 📱 Add to iPhone Home Screen

1. Open your GitHub Pages URL in **Safari**
2. Tap the **Share button** (box with arrow)
3. Tap **Add to Home Screen**
4. Name it **Oregon 70.3**
5. Tap **Add**

It now lives on your home screen and opens like an app.

---

## 🔄 How Auto-Updates Work

Every morning at **6:00 AM Pacific Time**, GitHub automatically:
1. Logs into your Garmin Connect account
2. Pulls all activities since April 21, 2026
3. Pulls last 60 days of sleep data
4. Updates the data files in your repository
5. Dashboard refreshes next time you open it

**You don't need to do anything** — just open the dashboard and your latest data is there.

---

## 📊 What Gets Updated Daily

- All new activities (swim, bike, run, bricks)
- TSS by week vs targets
- Bike NP trends
- Sleep scores, SpO2, resting HR
- Training analysis and weekly progress
- Days-to-race countdown

---

## 🛠 Manual Update

If you want to force an update anytime:
1. Go to your repository → **Actions**
2. Click **Update Dashboard Daily**
3. Click **Run workflow**

---

## ❓ Troubleshooting

**Dashboard shows "No activities loaded"**
→ The GitHub Action hasn't run yet. Go to Actions tab and trigger it manually.

**Action fails with login error**
→ Double-check your GARMIN_EMAIL and GARMIN_PASSWORD secrets are correct.

**Garmin MFA / 2-factor**
→ If you have 2FA on your Garmin account, temporarily disable it or create a separate Garmin account without 2FA for this integration.

**Dashboard URL not working**
→ Wait 5 minutes after enabling GitHub Pages. Check Settings → Pages to confirm it's enabled.

---

## 🏁 Race Info

- **IM 70.3 Oregon** · Salem, OR · July 19, 2026
- **IM California 140.6** · Sacramento, CA · October 18, 2026
- Bike NP target: **145–152w**
- Run pace target: **sub-9:10/mi**
- Overall goal: **Sub-6:00**
