# OUTIL: serveur_tableau_de_bord
# VERSION: 1
# RESUME: Serveur local du tableau de bord sur le PC de l'utilisateur (PowerShell 5.1, sans installation ni droits d'administrateur, lecture seule). Il sert la dernière page du tableau de bord (revues\tableau_de_bord\tableau_de_bord_vN.html) sur http://127.0.0.1:8771/ et ouvre le navigateur. La page passe alors en direct : toutes les 5 s, elle demande à /api/brut les événements du journal écrits depuis sa dernière lecture (curseur), et, s'ils ont changé, le planificateur, le registre des propositions, le cache des agents et l'état de l'ouvrier LM Studio ; elle refait l'agrégation dans le navigateur (même logique que tableau_de_bord collecter). Écoute sur 127.0.0.1 seulement : invisible du réseau.
# USAGE: lancer_tableau_de_bord_vN.cmd (double-clic) ; ou : powershell -NoProfile -ExecutionPolicy Bypass -File serveur_tableau_de_bord_v1.ps1 [-Racine <dossier 00_competences_claude>] [-Port 8771] [-SansNavigateur] [-DureeMax <s>] [-MaxEvenements 3000]
# ENTREES: <racine>\outils\_gestion\chemins_vN.json (noms des dossiers) ; <revues>\tableau_de_bord\tableau_de_bord_vN.html et agents_vN.json ; <journal>\AAAA-MM-JJ\*.json ; <taches>\planificateur_vN.json ; <propositions>\registre_propositions_vN.json ; Revision\00_espace_cloud_claude\file_lmstudio\journal\etat.json et entree\*.jsonl
# SORTIES: aucune écriture ; réponses HTTP : / (page), /api/ping, /api/brut?apres=<clé>&sig=<signature> (une ligne par enregistrement : M méta, E clé json, F nom source json)
# CATEGORIE: gouvernance
# BANC: tests/test_serveur_tableau_de_bord_v1.py
# REMPLACE: -
param([string]$Racine = '', [int]$Port = 8771, [switch]$SansNavigateur, [int]$DureeMax = 0, [int]$MaxEvenements = 3000)
$ErrorActionPreference = 'Stop'
$UTF8 = New-Object System.Text.UTF8Encoding $false
function P { return [IO.Path]::Combine([string[]]$args) }
if (-not $Racine) { $Racine = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) }
$Racine = [IO.Path]::GetFullPath($Racine)
if (-not [IO.Directory]::Exists((P $Racine 'outils'))) { Write-Host "Dossier de l'espace introuvable : $Racine (attendu : 00_competences_claude)"; exit 5 }

# ---------------- dossiers (registre central des chemins)
function Derniere($dossier, $base, $ext) {
    if (-not [IO.Directory]::Exists($dossier)) { return $null }
    $rx = '^' + [regex]::Escape($base) + '_v(\d+)\.' + [regex]::Escape($ext) + '$'; $meilleur = $null; $n = -1
    foreach ($f in [IO.Directory]::GetFiles($dossier)) {
        $m = [regex]::Match([IO.Path]::GetFileName($f), $rx)
        if ($m.Success -and [int]$m.Groups[1].Value -gt $n) { $n = [int]$m.Groups[1].Value; $meilleur = $f } }
    return $meilleur }
$CH = @{ journal = 'journal'; taches = 'taches'; propositions = 'propositions_a_reviser'; revues = 'revues' }   # valeurs par défaut de cc_lib_v4 (sans registre) ; le registre les remplace
$fc = Derniere (P $Racine 'outils' '_gestion') 'chemins' 'json'
if ($fc) { try { $j = [IO.File]::ReadAllText($fc, $UTF8) | ConvertFrom-Json; foreach ($k in @($CH.Keys)) { if ($j.chemins.$k) { $CH[$k] = [string]$j.chemins.$k } } } catch { Write-Host "Registre des chemins illisible : noms par defaut." } }
$LM = P (Split-Path -Parent $Racine) '00_espace_cloud_claude' 'file_lmstudio'

function Relatif($f) { return $f.Substring($Racine.Length).TrimStart('\', '/').Replace('\', '/') }
function UneLigne($t) { return ($t.Trim() -replace "[\r\n]+", ' ') }
function Lire($f) { try { return [IO.File]::ReadAllText($f, $UTF8) } catch { return $null } }

# ---------------- événements du journal après le curseur (ordre binaire des clés AAAA-MM-JJ/nom)
function Evenements($apres) {
    $J = P $Racine $CH.journal; $out = New-Object System.Collections.Generic.List[string]; $dern = $apres
    if (-not [IO.Directory]::Exists($J)) { return @{ lignes = $out; curseur = $apres; fin = $true } }
    $jours = [string[]]@([IO.Directory]::GetDirectories($J) | ForEach-Object { [IO.Path]::GetFileName($_) } | Where-Object { $_ -match '^\d{4}-\d\d-\d\d$' })
    [Array]::Sort($jours, [StringComparer]::Ordinal)
    $jA = ''; if ($apres.Length -ge 10) { $jA = $apres.Substring(0, 10) }
    $limite = [DateTime]::UtcNow.AddSeconds(-2)
    foreach ($jr in $jours) {
        if ([string]::CompareOrdinal($jr, $jA) -lt 0) { continue }
        $noms = [string[]]@([IO.Directory]::GetFiles((P $J $jr), '*.json') | ForEach-Object { [IO.Path]::GetFileName($_) })
        [Array]::Sort($noms, [StringComparer]::Ordinal)
        foreach ($n in $noms) {
            $cle = $jr + '/' + $n
            if ([string]::CompareOrdinal($cle, $apres) -le 0) { continue }
            $f = P $J $jr $n
            if ([IO.File]::GetLastWriteTimeUtc($f) -gt $limite) { return @{ lignes = $out; curseur = $dern; fin = $true } }   # en cours d'écriture : au passage suivant
            if ($out.Count -ge $MaxEvenements) { return @{ lignes = $out; curseur = $dern; fin = $false } }
            $t = Lire $f; if ($null -eq $t) { return @{ lignes = $out; curseur = $dern; fin = $true } }
            $out.Add("E`t$cle`t" + (UneLigne $t)); $dern = $cle } }
    return @{ lignes = $out; curseur = $dern; fin = $true } }

# ---------------- fichiers d'état (envoyés seulement quand leur signature change)
function Fichiers {
    $Fi = [ordered]@{
        planificateur = Derniere (P $Racine $CH.taches) 'planificateur' 'json'
        registre      = Derniere (P $Racine $CH.propositions) 'registre_propositions' 'json'
        agents        = Derniere (P $Racine $CH.revues 'tableau_de_bord') 'agents' 'json' }
    $sig = New-Object System.Text.StringBuilder; $lignes = New-Object System.Collections.Generic.List[string]
    foreach ($k in $Fi.Keys) { $f = $Fi[$k]   # PowerShell ignore la casse : $f et $F seraient la même variable
        if ($f) { [void]$sig.Append($k + '=' + [IO.Path]::GetFileName($f) + ':' + [IO.File]::GetLastWriteTimeUtc($f).Ticks + ';')
            $t = Lire $f; if ($null -ne $t) { $lignes.Add("F`t$k`t" + (Relatif $f) + "`t" + (UneLigne $t)) } } }
    if ([IO.Directory]::Exists($LM)) {
        $fe = P $LM 'journal' 'etat.json'; $et = 'null'
        if ([IO.File]::Exists($fe)) { $t = Lire $fe; if ($t -and $t.Trim()) { $et = UneLigne $t.TrimStart([char]0xFEFF) }; [void]$sig.Append('lm=' + [IO.File]::GetLastWriteTimeUtc($fe).Ticks + ';') }
        $n = 0; $de = P $LM 'entree'; if ([IO.Directory]::Exists($de)) { $n = @([IO.Directory]::GetFiles($de, '*.jsonl')).Count }
        [void]$sig.Append('lots=' + $n + ';')
        $lignes.Add("F`tlmstudio`t-`t{`"etat`":" + $et + ",`"lots_entree`":" + $n + "}") }
    $s = $sig.ToString(); $h = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($UTF8.GetBytes($s))).Replace('-', '').Substring(0, 16).ToLower()
    return @{ sig = $h; lignes = $lignes } }

function Brut($apres, $sigClient) {
    $E = Evenements $apres; $F = Fichiers
    $b = New-Object System.Text.StringBuilder
    $meta = @{ curseur = $E.curseur; fin = $E.fin; sig = $F.sig; n = $E.lignes.Count; serveur = 'serveur_tableau_de_bord'; maintenant = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ') }
    [void]$b.Append("M`t" + ($meta | ConvertTo-Json -Compress) + "`n")
    foreach ($l in $E.lignes) { [void]$b.Append($l + "`n") }
    if ($F.sig -ne $sigClient) { foreach ($l in $F.lignes) { [void]$b.Append($l + "`n") } }
    return $b.ToString() }

function Page {
    $f = Derniere (P $Racine $CH.revues 'tableau_de_bord') 'tableau_de_bord' 'html'
    if (-not $f) { return "<!doctype html><html lang=`"fr`"><head><meta charset=`"utf-8`"><title>Tableau de bord</title></head><body><p>Aucune page du tableau de bord (tableau_de_bord_vN.html) dans $($CH.revues)\tableau_de_bord.</p></body></html>" }
    $t = Lire $f; $i = $t.IndexOf('<div class="page">'); if ($i -lt 0) { $i = 0 }
    return "<!doctype html>`n<html lang=`"fr`"><head><meta charset=`"utf-8`"><meta name=`"viewport`" content=`"width=device-width, initial-scale=1, viewport-fit=cover`">`n" + $t.Substring(0, $i) + "`n<style>body{margin:0}</style></head><body>`n" + $t.Substring($i) + "`n</body></html>" }

# ---------------- HTTP minimal (TcpListener sur 127.0.0.1 : aucun droit d'administrateur)
function Repondre($s, $code, $type, $texte) {
    $b = $UTF8.GetBytes($texte)
    $h = "HTTP/1.1 $code`r`nContent-Type: $type; charset=utf-8`r`nContent-Length: $($b.Length)`r`nCache-Control: no-store`r`nX-Content-Type-Options: nosniff`r`nConnection: close`r`n`r`n"
    $hb = [Text.Encoding]::ASCII.GetBytes($h); $s.Write($hb, 0, $hb.Length); $s.Write($b, 0, $b.Length); $s.Flush() }
function Parametres($q) {
    $r = @{}; if (-not $q) { return $r }
    foreach ($x in $q.Split('&')) { if (-not $x) { continue }; $kv = $x.Split('=', 2); $v = ''; if ($kv.Length -gt 1) { $v = [Uri]::UnescapeDataString($kv[1].Replace('+', ' ')) }; $r[[Uri]::UnescapeDataString($kv[0])] = $v }
    return $r }
function Servir($cl) {
    try {
        $s = $cl.GetStream(); $s.ReadTimeout = 2000; $buf = New-Object byte[] 8192; $req = ''
        do { $k = $s.Read($buf, 0, $buf.Length); if ($k -le 0) { break }; $req += [Text.Encoding]::ASCII.GetString($buf, 0, $k) } while ($req.IndexOf("`r`n`r`n") -lt 0 -and $req.Length -lt 65536)
        $p = (($req -split "`r`n")[0]) -split ' '; $meth = $p[0]; $cible = ''; if ($p.Length -gt 1) { $cible = $p[1] }
        $morceaux = $cible.Split('?', 2); $chemin = $morceaux[0]; $q = ''; if ($morceaux.Length -gt 1) { $q = $morceaux[1] }
        if ($meth -ne 'GET') { Repondre $s '405 Method Not Allowed' 'application/json' '{"ok":false}' }
        elseif ($chemin -eq '/') { Repondre $s '200 OK' 'text/html' (Page) }
        elseif ($chemin -eq '/api/ping') { Repondre $s '200 OK' 'application/json' '{"ok":true,"serveur":"serveur_tableau_de_bord","version":1}' }
        elseif ($chemin -eq '/api/brut') { $a = Parametres $q; $ap = ''; if ($a.ContainsKey('apres')) { $ap = $a['apres'] }; $sg = ''; if ($a.ContainsKey('sig')) { $sg = $a['sig'] }
            Repondre $s '200 OK' 'text/plain' (Brut $ap $sg) }
        else { Repondre $s '404 Not Found' 'application/json' '{"ok":false}' }
    } catch { $m = 'erreur : ' + $_.Exception.Message + ' ' + $_.ScriptStackTrace; Write-Host $m; try { Repondre $s '500 Internal Server Error' 'text/plain' $m } catch {} }
    finally { $cl.Close() } }

$L = $null
for ($p = $Port; $p -lt $Port + 9; $p++) {
    try { $L = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p); $L.Start(); $Port = $p; break } catch { $L = $null } }
if (-not $L) { Write-Host "Aucun port libre de $Port a $($Port + 8) : un autre serveur du tableau de bord tourne peut-etre."; exit 4 }
$url = "http://127.0.0.1:$Port/"
Write-Host "Tableau de bord en direct : $url"
Write-Host "Espace : $Racine"
Write-Host "Fermer cette fenetre (ou Ctrl+C) pour arreter le serveur. Il ne lit que des fichiers et n'ecrit rien."
if (-not $SansNavigateur) { try { Start-Process $url } catch { Write-Host "Ouvrir $url dans le navigateur." } }
$debut = [DateTime]::UtcNow
try {
    while ($true) {
        if ($DureeMax -gt 0 -and ([DateTime]::UtcNow - $debut).TotalSeconds -ge $DureeMax) { break }
        if ($L.Pending()) { Servir ($L.AcceptTcpClient()) } else { Start-Sleep -Milliseconds 40 } } }
finally { $L.Stop() }
exit 0
