@echo off
rem OUTIL: lancer_tableau_de_bord
rem VERSION: 1
rem RESUME: Lanceur du tableau de bord en direct sur le PC : demarre la derniere version de serveur_tableau_de_bord (PowerShell, sans installation), qui ouvre le navigateur sur http://127.0.0.1:8771/ . Fermer cette fenetre arrete le serveur.
rem USAGE: double-clic sur ce fichier
rem ENTREES: ..\serveur_tableau_de_bord\serveur_tableau_de_bord_vN.ps1 (derniere version)
rem SORTIES: aucune (console)
rem CATEGORIE: gouvernance
rem BANC: tests/test_serveur_tableau_de_bord_v1.py
rem REMPLACE: -
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d = Join-Path '%~dp0' '..\serveur_tableau_de_bord'; $f = Get-ChildItem -LiteralPath $d -Filter 'serveur_tableau_de_bord_v*.ps1' | Sort-Object { [int]($_.BaseName -replace '^.*_v', '') } | Select-Object -Last 1; if (-not $f) { Write-Host 'serveur_tableau_de_bord introuvable'; exit 5 }; & $f.FullName; exit $LASTEXITCODE"
echo Serveur du tableau de bord arrete (code %ERRORLEVEL% : 0 normal, 4 port occupe, 5 dossier introuvable).
pause
