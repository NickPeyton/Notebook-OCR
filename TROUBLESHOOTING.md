# Troubleshooting

## Check if the pipeline is running

```powershell
Get-Process pythonw
```

You should see two `pythonw` processes. If you see none, the pipeline is not running.

---

## Start / stop the pipeline manually

The pipeline is managed by Windows Task Scheduler.

```powershell
Start-ScheduledTask -TaskName "NotebookOCR"
Stop-ScheduledTask -TaskName "NotebookOCR"
```

To restart:

```powershell
Stop-ScheduledTask -TaskName "NotebookOCR"
Start-ScheduledTask -TaskName "NotebookOCR"
```

---

## View logs

```powershell
Get-Content "C:\Users\nicho\My Drive\10_Reading\Notebook OCR\ocr_pipeline.log" -Tail 50
```

To watch live:

```powershell
Get-Content "C:\Users\nicho\My Drive\10_Reading\Notebook OCR\ocr_pipeline.log" -Tail 50 -Wait
```

---

## Pipeline crashed / sent an alert email

The pipeline retries failed files 5 times with exponential backoff. If all retries fail, it sends an alert to `nicholas.and.dixie@gmail.com` and stops.

1. Check the log for the error and traceback (see above)
2. If the offending image is corrupted or unreadable, move it out of the `notebooks/` folder
3. Restart the pipeline:
   ```powershell
   Start-ScheduledTask -TaskName "NotebookOCR"
   ```

---

## A file was processed with wrong / missing bib data

Check `incomplete_bib.txt` — sources whose bib data could not be found are logged there with title, author, year, notebook, and page. You can look them up manually and add entries to `library.bib`.

---

## A file was not processed at all

The pipeline tracks processed files in `processed_files.json`. If a file is listed there but the output is missing or wrong, remove its entry from `processed_files.json` and drop the image back into the `notebooks/` subfolder — the watcher will pick it up again.

---

## Task Scheduler: verify the task is configured correctly

```powershell
Get-ScheduledTask -TaskName "NotebookOCR" | Get-ScheduledTaskInfo
```

To see the trigger:

```powershell
Get-ScheduledTask -TaskName "NotebookOCR" | Select-Object -ExpandProperty Triggers
```

`Enabled: True` with `UserId: NICK_LAPTOP\nicho` confirms it will auto-start on login.

---

## Re-register the task from scratch

If the task gets corrupted or deleted:

```powershell
Register-ScheduledTask -TaskName 'NotebookOCR' -Xml (Get-Content 'C:\Users\nicho\My Drive\10_Reading\Notebook OCR\notebook_ocr_task.xml' -Raw) -Force
```

Run this from an **admin PowerShell**.
