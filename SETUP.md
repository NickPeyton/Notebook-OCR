# Setup Guide

- [Windows](#windows-setup)
- [Raspberry Pi](#raspberry-pi-setup)

---

# Windows Setup

The pipeline runs silently in the background and starts automatically when you log in. No console window, no manual steps after the first-time setup.

## Prerequisites

- Windows 10 or 11
- Python 3.11+ — download from https://www.python.org/downloads/ (check "Add Python to PATH" during install)
- The project folder synced to your machine via Google Drive for Desktop (the folder should already be in your Drive)

---

## 1. Get the project folder

If Google Drive for Desktop is installed, the folder will already be available at a path like:

```
C:\Users\<yourname>\My Drive\10_Reading\Notebook OCR
```

If not, install Google Drive for Desktop and sign in — it will sync automatically.

---

## 2. Open PowerShell in the project folder

1. Open File Explorer and navigate to the `Notebook OCR` folder
2. Click the address bar, type `powershell`, and press Enter

This opens a PowerShell window already in the right folder.

---

## 3. Create the Python environment and install dependencies

Paste this block into PowerShell and press Enter:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

This only needs to be done once.

---

## 4. Configure your credentials

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in the three values:

```
GEMINI_API_KEY=your_gemini_api_key
GMAIL_ADDRESS=your_gmail@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
```

**Getting a Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords (requires 2-Step Verification to be enabled)
2. Create a new app password — name it anything (e.g. "Notebook OCR")
3. Copy the 16-character code into `.env` **without spaces**

Save and close Notepad.

---

## 5. Register the startup task

This registers the pipeline to start automatically every time you log in. Open **PowerShell as Administrator** (right-click the Start menu → "Windows PowerShell (Admin)") and run:

```powershell
Register-ScheduledTask -TaskName 'NotebookOCR' -Xml (Get-Content 'C:\Users\<yourname>\My Drive\10_Reading\Notebook OCR\notebook_ocr_task.xml' -Raw) -Force
```

Replace `<yourname>` with your actual Windows username.

---

## 6. Start it now (without rebooting)

```powershell
Start-ScheduledTask -TaskName "NotebookOCR"
```

---

## 7. Verify it's running

```powershell
Get-Process pythonw
```

You should see two `pythonw` processes. That's correct — one is the main pipeline, the other is the file watcher.

From here the pipeline runs automatically. New images dropped into any subfolder of `notebooks/` will be picked up and processed. Output goes to `obsidian_notes/`, `library.bib`, and `index.json` — all synced back to Google Drive automatically.

---

# Raspberry Pi Setup

## Prerequisites
- Raspberry Pi running Raspberry Pi OS (64-bit recommended)
- Python 3.11+
- Internet connection
- Google Drive folder mirrored locally (see step 3)

---

## 1. Clone the repository

```bash
git clone <your-repo-url> /home/pi/notebook-ocr
cd /home/pi/notebook-ocr
```

---

## 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`pillow-heif` requires `libheif`. If the pip install fails, install it first:

```bash
sudo apt update
sudo apt install -y libheif-dev libde265-dev
pip install pillow-heif
```

---

## 3. Google Drive sync with rclone

Install rclone and configure a Google Drive remote named `gdrive`:

```bash
sudo apt install -y rclone
rclone config  # follow prompts, name the remote "gdrive"
```

Mirror the notebooks folder to the Pi (run this once manually to do the initial sync):

```bash
rclone sync gdrive:"Notebook OCR" /home/pi/notebook-ocr --exclude ".git/**"
```

To keep it continuously synced, add a cron job:

```bash
crontab -e
```

Add this line (syncs every 2 minutes):

```
*/2 * * * * rclone sync gdrive:"Notebook OCR" /home/pi/notebook-ocr --exclude ".git/**" >> /home/pi/rclone.log 2>&1
```

---

## 4. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in:

```
GEMINI_API_KEY=your_gemini_api_key
GMAIL_ADDRESS=your_gmail@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
```

To generate a Gmail App Password:
1. Go to https://myaccount.google.com/apppasswords
2. Sign in, select "Mail" and "Other (custom name)"
3. Copy the 16-character password into `.env`

---

## 5. Install the systemd service

```bash
sudo cp notebook_ocr.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable notebook_ocr
sudo systemctl start notebook_ocr
```

Check it's running:

```bash
sudo systemctl status notebook_ocr
```

---

## 6. Checking logs

View live logs via journald:

```bash
journalctl -u notebook_ocr -f
```

Or check the rotating log file directly:

```bash
tail -f /home/pi/notebook-ocr/ocr_pipeline.log
```

---

## 7. Stopping / restarting the service

```bash
sudo systemctl stop notebook_ocr
sudo systemctl restart notebook_ocr
```
