@echo off
rem OUTIL: lancer_worker_lmstudio
rem VERSION: 4
rem RESUME: Lanceur de l'ouvrier LM Studio. Il demarre la derniere version de worker_lmstudio dans sa copie installee (Revision\00_espace_cloud_claude\file_lmstudio\outil\), qu'il soit lance depuis ce dossier d'installation ou depuis 00_competences_claude\outils\lancer_worker_lmstudio\. La copie source (outils\worker_lmstudio\) n'est jamais lancee : l'ouvrier deduit la file de son propre emplacement (dossier parent contenant entree\).
rem USAGE: double-clic ; gestion de l'ouvrier : http://127.0.0.1:8770/
rem ENTREES: worker_lmstudio_vN.ps1 du meme dossier, sinon de ..\..\..\00_espace_cloud_claude\file_lmstudio\outil\ (derniere version, dossier parent avec entree\)
rem SORTIES: aucune (console) ; codes : 0 demande, 2 LM Studio interrompu, 3 file vide, 4 port occupe, 5 ouvrier installe introuvable
rem CATEGORIE: delegation_locale
rem BANC: tests/test_lancer_worker_lmstudio_v4.py
rem REMPLACE: lancer_worker_lmstudio_v3 (lancait worker_lmstudio_v3.ps1 du meme dossier seulement : echouait depuis outils\ apres le rangement d'un outil par dossier ; version du script ecrite en dur)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ici = '%~dp0'; $cands = @($ici, (Join-Path $ici '..\..\..\00_espace_cloud_claude\file_lmstudio\outil')); foreach ($d in $cands) { if (-not (Test-Path -LiteralPath $d)) { continue }; $f = Get-ChildItem -LiteralPath $d -Filter 'worker_lmstudio_v*.ps1' -ErrorAction SilentlyContinue | Sort-Object { [int]($_.BaseName -replace '^.*_v', '') } | Select-Object -Last 1; if (-not $f) { continue }; if (-not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $f.DirectoryName) 'entree'))) { continue }; Write-Host ('Ouvrier : ' + $f.FullName); Write-Host 'Page de gestion de l''ouvrier : http://127.0.0.1:8770/'; & $f.FullName; exit $LASTEXITCODE }; Write-Host 'Ouvrier installe introuvable : attendu dans Revision\00_espace_cloud_claude\file_lmstudio\outil\ (file_lmstudio installer).'; exit 5"
echo Ouvrier arrete (code %ERRORLEVEL% : 0 demande, 2 LM Studio interrompu, 3 file vide, 4 port occupe, 5 ouvrier installe introuvable).
pause
