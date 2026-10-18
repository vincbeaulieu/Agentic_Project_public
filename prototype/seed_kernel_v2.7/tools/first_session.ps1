# First session on Windows with LM Studio (run from prototype\seed_kernel_v2.2 in PowerShell).
# Runs the non-interactive steps and leaves all results under state\ (readable by the reviewer):
#   tests -> init -> models probe -> models test -> qualify -> quickstart -> one propose cycle
# Approve / apply remain interactive commands (they require the typed phrase).
$ErrorActionPreference = "Continue"
$log = "state\first_session.log"
New-Item -ItemType Directory -Force -Path state | Out-Null
"first session $(Get-Date -Format s)" | Tee-Object -FilePath $log
python --version 2>&1 | Tee-Object -FilePath $log -Append
python -m pytest -q -p no:cacheprovider 2>&1 | Select-Object -Last 1 | Tee-Object -FilePath $log -Append
python -m kernel init 2>&1 | Out-Null
"--- models probe" | Tee-Object -FilePath $log -Append
python -m kernel models probe 2>&1 | Tee-Object -FilePath $log -Append
"--- models test proposer" | Tee-Object -FilePath $log -Append
python -m kernel models test proposer 2>&1 | Tee-Object -FilePath $log -Append
"--- qualify proposer" | Tee-Object -FilePath $log -Append
python -m kernel qualify proposer 2>&1 | Tee-Object -FilePath $log -Append
"--- quickstart" | Tee-Object -FilePath $log -Append
python -m kernel quickstart 2>&1 | Tee-Object -FilePath $log -Append
"--- propose (T-001)" | Tee-Object -FilePath $log -Append
python -m kernel propose 2>&1 | Tee-Object -FilePath $log -Append
"--- status" | Tee-Object -FilePath $log -Append
python -m kernel status 2>&1 | Tee-Object -FilePath $log -Append
"done. Pending requests are listed above; review with: python -m kernel review <req-id>" | Tee-Object -FilePath $log -Append
