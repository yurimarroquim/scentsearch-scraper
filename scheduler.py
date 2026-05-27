import time
import subprocess
from datetime import datetime, timezone, timedelta

BRASILIA = timezone(timedelta(hours=-3))
sync_ran_today = None
dedup_ran_today = None
alert_ran_today = None

print("Scheduler iniciado.", flush=True)

while True:
    agora = datetime.now(BRASILIA)
    hoje = agora.date()

    if agora.hour == 3 and agora.minute == 0 and sync_ran_today != hoje:
        print(f"[{agora}] Executando sync_match...", flush=True)
        subprocess.run(
            ["python3", "sync_match.py"],
            cwd="/home/runner/workspace/artifacts/scentsearch-scraper",
        )
        sync_ran_today = hoje

    if agora.hour == 4 and agora.minute == 0 and dedup_ran_today != hoje:
        print(f"[{agora}] Executando dedup_geral...", flush=True)
        subprocess.run(
            ["python3", "dedup_geral.py", "--apply"],
            cwd="/home/runner/workspace/artifacts/scentsearch-scraper",
        )
        dedup_ran_today = hoje

    if agora.hour == 8 and agora.minute == 0 and alert_ran_today != hoje:
        print(f"[{agora}] Executando alert_checker...", flush=True)
        subprocess.run(
            ["python3", "alert_checker.py"],
            cwd="/home/runner/workspace/artifacts/scentsearch-scraper",
        )
        alert_ran_today = hoje

    time.sleep(30)
