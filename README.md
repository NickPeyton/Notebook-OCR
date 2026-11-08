# Notebook OCR

Automatically OCRs handwritten notebook pages and produces structured Markdown notes for Obsidian. The pipeline watches for new photos of notebook pages (synced via Google Drive), sends them to Google's Gemini API for transcription, and outputs one `.md` file per source with YAML metadata. It runs silently in the background and starts automatically on login.

## What it does

1. Watches the `notebooks/` folder for new images (`.heic`, `.jpg`, `.png`). It also checks the folders when it starts and regularly while running, so photos added while your computer was off are not missed. Pages are always processed in filename order, and it waits until Google Drive has finished downloading a batch (no new photo for a minute) before starting
2. Converts HEIC photos to JPEG
3. Sends each image to the Gemini API, which reads your handwriting and extracts structured notes
4. Creates one Markdown file per source in `obsidian_notes/`, with metadata (title, author, year, notebook, page). Existing notes are only ever added to, never overwritten
5. Detects continuation pages and appends them to the correct existing file. If it can't work out which note a page belongs to, the text is saved in `obsidian_notes/_unmatched_continuations.md` instead of being lost
6. Updates `index.json` with metadata for every processed page
7. Checks `library.bib` for each source and adds new BibTeX entries automatically (sources it cannot identify are logged to `incomplete_bib.txt` for manual lookup)

## Folder layout

```
notebooks/
  blue_1/            # one subfolder per physical notebook
  blue_2/
  ...
obsidian_notes/      # output Markdown files (one per source)
index.json           # global index of all processed sources
library.bib          # cumulative BibTeX bibliography
incomplete_bib.txt   # sources whose bib data could not be found automatically
model_config.json    # which Gemini models to use, in order of preference
rate_usage.json      # auto-generated — which models are paused after hitting a usage limit
processed_files.json # auto-generated — tracks which images have been processed
ocr_pipeline.log     # auto-generated — rotating log file
```

## Prerequisites

- **Python 3.11 or later**. Download from https://www.python.org/downloads/. During installation, check "Add Python to PATH".
- **Google Drive for Desktop** (Windows) or **rclone** (Raspberry Pi) to sync the project folder.
- A **Gemini API key**. Get one free at https://aistudio.google.com/apikey.
- A **Gmail account with 2-Step Verification enabled**, to allow the pipeline to send you error alerts by email.

---

## Setup

### Windows

#### 1. Locate the project folder

If Google Drive for Desktop is installed, the folder is already on your machine at:

```
C:\Users\<yourname>\My Drive\10_Reading\Notebook OCR
```

#### 2. Open a terminal in the project folder

Open File Explorer, navigate to the `Notebook OCR` folder, click the address bar, type `powershell`, and press Enter.

#### 3. Create the Python environment

Paste this into PowerShell and press Enter:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

This only needs to be done once. If you later add packages to `requirements.txt`, re-run the second line.

#### 4. Configure your credentials

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

**To get a Gmail App Password:**

1. Go to https://myaccount.google.com/apppasswords (you must have 2-Step Verification turned on first)
2. Create a new app password — name it anything (e.g. "Notebook OCR")
3. Copy the 16-character code into `.env` without spaces

Save and close Notepad.

#### 5. Register the automatic startup task

Open **PowerShell as Administrator** (right-click the Start menu, choose "Windows PowerShell (Admin)") and run:

```powershell
Register-ScheduledTask -TaskName 'NotebookOCR' -Xml (Get-Content 'C:\Users\<yourname>\My Drive\10_Reading\Notebook OCR\notebook_ocr_task.xml' -Raw) -Force
```

Replace `<yourname>` with your Windows username. From now on, the pipeline will start automatically every time you log in.

#### 6. Start it now (without rebooting)

```powershell
Start-ScheduledTask -TaskName "NotebookOCR"
```

#### 7. Verify it's running

```powershell
Get-Process pythonw
```

You should see two `pythonw` processes (the main pipeline and the file watcher).

---

### Raspberry Pi

#### 1. Clone the repository

```bash
git clone <your-repo-url> /home/pi/notebook-ocr
cd /home/pi/notebook-ocr
```

#### 2. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If `pillow-heif` fails to install, you need the system library first:

```bash
sudo apt update
sudo apt install -y libheif-dev libde265-dev
pip install pillow-heif
```

#### 3. Set up Google Drive sync with rclone

```bash
sudo apt install -y rclone
rclone config   # follow the prompts; name the remote "gdrive"
```

Do an initial sync:

```bash
rclone sync gdrive:"Notebook OCR" /home/pi/notebook-ocr --exclude ".git/**"
```

To keep it continuously synced, add a cron job (`crontab -e`) that runs every 2 minutes:

```
*/2 * * * * rclone sync gdrive:"Notebook OCR" /home/pi/notebook-ocr --exclude ".git/**" >> /home/pi/rclone.log 2>&1
```

#### 4. Configure your credentials

```bash
cp .env.example .env
nano .env
```

Fill in `GEMINI_API_KEY`, `GMAIL_ADDRESS`, and `GMAIL_APP_PASSWORD` (see the Windows section above for how to get an app password).

#### 5. Install and start the service

```bash
sudo cp notebook_ocr.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable notebook_ocr
sudo systemctl start notebook_ocr
```

Verify it's running:

```bash
sudo systemctl status notebook_ocr
```

---

## Day-to-day use

Once the pipeline is running, there is nothing to do manually. Take a photo of a notebook page on your phone, let it sync to the appropriate `notebooks/` subfolder via Google Drive, and the pipeline will process it automatically. Output appears in `obsidian_notes/`.

### Creating a new notebook

Create a new subfolder inside `notebooks/` (e.g. `notebooks/red_1/`). The pipeline watches recursively, so new folders are detected automatically without restarting.

### Checking what has been processed

Open `index.json` — it lists every source with title, author, year, notebook, page range, and the name of the output Markdown file.

### Testing a single page

To see what the pipeline would produce for one photo, without changing any of your real notes, open PowerShell in the project folder and run:

```powershell
.venv\Scripts\python test_run.py notebooks\red_1\IMG_2785.jpg
```

(Leave out the image path to use a default page.) It works on a temporary copy of the project, prints the note text, index changes and bibliography entries it would have added, and tells you where the temporary folder is. Each run uses one of your daily Gemini requests. It is safe to run while the background pipeline is running.

### Re-processing an image

If a file was processed incorrectly, remove its entry from `processed_files.json` (make sure the image is still in, or put it back into, its `notebooks/` subfolder). The pipeline will pick it up again within 5 minutes. Note that the new text is added to the existing note, so delete the bad text from the note first.

### Gemini usage limits

You don't need to set or update usage limits. When Gemini says a model has reached its limit, the pipeline pauses that model (for a minute, or until the daily reset at midnight US Pacific time) and switches to the next one in `model_config.json`. The log records which limit was hit.

If you add more pages than the free daily allowance covers, nothing goes wrong: once every model is used up, the pipeline waits for the daily reset and carries on, in order, the next day. Likewise, if your computer has no internet connection, it waits and tries again every minute.

If Google retires a model, edit the list in `model_config.json` (most preferred first), e.g.:

```json
["gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-flash"]
```

---

## Troubleshooting

### Is the pipeline running?

**Windows:**
```powershell
Get-Process pythonw
```
Two `pythonw` processes = running. None = not running.

**Raspberry Pi:**
```bash
sudo systemctl status notebook_ocr
```

### Starting and stopping

**Windows:**
```powershell
Start-ScheduledTask -TaskName "NotebookOCR"
Stop-ScheduledTask -TaskName "NotebookOCR"
```

**Raspberry Pi:**
```bash
sudo systemctl start notebook_ocr
sudo systemctl stop notebook_ocr
sudo systemctl restart notebook_ocr
```

### Viewing logs

**Windows:**
```powershell
Get-Content "C:\Users\nicho\My Drive\10_Reading\Notebook OCR\ocr_pipeline.log" -Tail 50
```

Add `-Wait` to watch live.

**Raspberry Pi:**
```bash
journalctl -u notebook_ocr -f
# or
tail -f /home/pi/notebook-ocr/ocr_pipeline.log
```

### The pipeline crashed and sent an alert email

The pipeline retries failed Gemini requests 5 times, waiting longer each time. If something still fails — or anything else goes wrong, such as a damaged image — it sends an email to `nicholas.and.dixie@gmail.com` saying which file failed, and stops. (Running out of daily Gemini allowance, or losing your internet connection, does not stop it — it just waits.)

1. Check the log for the error and traceback
2. If the offending image is corrupted, move it out of `notebooks/`
3. Restart the pipeline (see above)

### Bibliography data is missing or wrong

Check `incomplete_bib.txt` — sources whose bibliographic data could not be found automatically are listed there. You can look them up manually and add entries to `library.bib`.

Before adding anything, the pipeline checks whether `library.bib` already has a work with the same title (ignoring the subtitle), so different editions of a book you already have (e.g. a 1957 reprint of a 1944 book) are not added twice.

### A page is missing from its note

Check `obsidian_notes/_unmatched_continuations.md`. Pages the pipeline couldn't match to a note are saved there, with the image name, notebook and page number. Copy the text into the right note, then delete it from this file.

### Re-registering the Windows task from scratch

If the scheduled task gets corrupted or deleted, open an admin PowerShell and run:

```powershell
Register-ScheduledTask -TaskName 'NotebookOCR' -Xml (Get-Content 'C:\Users\nicho\My Drive\10_Reading\Notebook OCR\notebook_ocr_task.xml' -Raw) -Force
```

### Verifying the Windows scheduled task

```powershell
Get-ScheduledTask -TaskName "NotebookOCR" | Get-ScheduledTaskInfo
Get-ScheduledTask -TaskName "NotebookOCR" | Select-Object -ExpandProperty Triggers
```

`Enabled: True` with your username confirms it will auto-start on login.
