# OUTIL: worker_lmstudio
# VERSION: 3
# RESUME: Ouvrier sur le PC de l'utilisateur (PowerShell 5.1, sans installation ni droits d'administrateur) : traite la file de micro-tâches (fichiers JSONL) avec LM Studio (127.0.0.1:1234) ; ordonnanceur à priorités avec vieillissement (pas de famine) et regroupement par modèle ; API locale de gestion sur 127.0.0.1:8770 (page de contrôle, état, pause, reprise, arrêt immédiat qui annule l'appel en cours) ; s'arrête seul si le serveur LM Studio est interrompu, si la file reste vide, ou sur demande ; garde-fous contre le gel du PC (délai par appel, pause si la mémoire libre baisse, priorité basse, cadence bornée).
# USAGE: lancer_worker_lmstudio_v3.cmd (double-clic) ; gestion : http://127.0.0.1:8770/ ; réglages facultatifs : <file>\config_worker.json
# ENTREES: <file>\entree\*.jsonl : une tâche par ligne {id, prio (0 urgent à 3 fond), modele, consigne (fichier <file>\consignes\<nom>.txt) ou systeme, u, valeurs [..], max_tokens, type (chat|embedding)}
# SORTIES: <file>\sortie\<lot>_resultats.jsonl {id, modele, r, ms, tokens, essai, erreur, fin} ; <file>\journal\etat.json ; <file>\journal\worker.log ; lots traités déplacés dans <file>\traite\
# CATEGORIE: delegation_locale
# BANC: -
# REMPLACE: worker_lmstudio_v2 (arrêt seulement par fermeture de la fenêtre ou fichier ARRET, appel bloquant sans annulation, attente sans fin si LM Studio est arrêté)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$Racine = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)   # ...\file_lmstudio
$UTF8 = New-Object System.Text.UTF8Encoding $false

# ---------------- réglages (surchargeables par config_worker.json)
$C = @{ port = 8770; url_lmstudio = 'http://127.0.0.1:1234'; vieillissement_min = 10.0; fenetre_modele = 1.0
        delai_tache_s = 180; pause_entre_taches_ms = 100; arret_si_lmstudio_absent_min = 3; arret_si_inactif_min = 30
        memoire_libre_min_mo = 1500; essais = 3 }
$fc = Join-Path $Racine 'config_worker.json'
if (Test-Path $fc) { $j = [IO.File]::ReadAllText($fc, $UTF8) | ConvertFrom-Json; foreach ($p in $j.PSObject.Properties) { $C[$p.Name] = $p.Value } }
foreach ($d in 'entree', 'encours', 'sortie', 'traite', 'journal', 'consignes') { New-Item -ItemType Directory -Force -Path (Join-Path $Racine $d) | Out-Null }
try { (Get-Process -Id $PID).PriorityClass = 'BelowNormal' } catch {}

$file = New-Object System.Collections.ArrayList
$lots = @{}; $consignes = @{}; $seq = 0
$etat = @{ version = 3; debut = (Get-Date).ToString('s'); statut = 'démarrage'; raison_arret = $null; traites = 0; erreurs = 0
           modele = ''; dernier = ''; tache_en_cours = $null; en_attente = 0; lots = 0; port = $C.port; lmstudio_joignable = $null }
$script:commande = $null      # pause | reprendre | arreter (posée par l'API ou le fichier ARRET)
$script:enPause = $false

function Journal($msg) { [IO.File]::AppendAllText((Join-Path $Racine 'journal\worker.log'), ((Get-Date).ToString('s') + ' ' + $msg + "`r`n"), $UTF8); Write-Host ((Get-Date).ToString('HH:mm:ss') + ' ' + $msg) }
function Ecrire-Etat { $etat.en_attente = $file.Count; $etat.lots = $lots.Count; $etat.maj = (Get-Date).ToString('s')
    $t = Join-Path $Racine 'journal\etat.json.tmp'; [IO.File]::WriteAllText($t, ($etat | ConvertTo-Json -Compress -Depth 4), $UTF8)
    Move-Item -Force $t (Join-Path $Racine 'journal\etat.json') }

# ---------------- API locale de gestion (TcpListener sur 127.0.0.1 : aucun droit d'administrateur)
$PAGE = @'
<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Ouvrier LM Studio</title>
<style>body{font:15px system-ui,sans-serif;margin:24px;max-width:720px;color:#222;background:#fafafa}button{font:inherit;padding:8px 16px;margin-right:8px;cursor:pointer}
pre{background:#fff;border:1px solid #ddd;padding:12px;white-space:pre-wrap}#s{font-weight:600}</style></head><body>
<h1>Ouvrier LM Studio</h1><p>Statut : <span id="s">…</span></p>
<p><button onclick="c('pause')">Pause</button><button onclick="c('reprendre')">Reprendre</button><button onclick="if(confirm('Arrêter l\'ouvrier ? L\'appel en cours est annulé et la tâche reste en file.'))c('arreter')">Arrêter</button></p>
<pre id="e">…</pre>
<script>async function c(x){await fetch('/'+x,{method:'POST'});m()}
async function m(){try{const r=await fetch('/etat');const j=await r.json();document.getElementById('s').textContent=j.statut;document.getElementById('e').textContent=JSON.stringify(j,null,1)}catch(e){document.getElementById('s').textContent='ouvrier arrêté ou injoignable'}}
m();setInterval(m,2000)</script></body></html>
'@
try { $L = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, [int]$C.port); $L.Start() }
catch { Write-Host "Port $($C.port) déjà utilisé : un autre ouvrier tourne peut-être (http://127.0.0.1:$($C.port)/)."; exit 4 }

function Repondre($s, $code, $type, $texte) {
    $b = $UTF8.GetBytes($texte)
    $h = "HTTP/1.1 $code`r`nContent-Type: $type; charset=utf-8`r`nContent-Length: $($b.Length)`r`nCache-Control: no-store`r`nConnection: close`r`n`r`n"
    $hb = [Text.Encoding]::ASCII.GetBytes($h); $s.Write($hb, 0, $hb.Length); $s.Write($b, 0, $b.Length); $s.Flush() }
function Servir-Controle {
    while ($L.Pending()) {
        $cl = $L.AcceptTcpClient()
        try {
            $s = $cl.GetStream(); $s.ReadTimeout = 1000; $buf = New-Object byte[] 8192; $req = ''
            do { $k = $s.Read($buf, 0, $buf.Length); if ($k -le 0) { break }; $req += [Text.Encoding]::ASCII.GetString($buf, 0, $k) } while ($req.IndexOf("`r`n`r`n") -lt 0 -and $req.Length -lt 65536)
            $p = (($req -split "`r`n")[0]) -split ' '; $meth = $p[0]; $chemin = ($p[1] -split '\?')[0]
            $orig = [regex]::Match($req, '(?im)^Origin:\s*(\S+)').Groups[1].Value
            $origOk = (-not $orig) -or ($orig -eq "http://127.0.0.1:$($C.port)") -or ($orig -eq "http://localhost:$($C.port)")
            if ($meth -eq 'GET' -and $chemin -eq '/') { Repondre $s '200 OK' 'text/html' $PAGE }
            elseif ($meth -eq 'GET' -and $chemin -eq '/etat') { $etat.en_attente = $file.Count; Repondre $s '200 OK' 'application/json' ($etat | ConvertTo-Json -Compress -Depth 4) }
            elseif ($meth -eq 'POST' -and @('/pause', '/reprendre', '/arreter') -contains $chemin) {
                if (-not $origOk) { Repondre $s '403 Forbidden' 'application/json' '{"ok":false,"raison":"origine refusée"}' }
                else { $script:commande = $chemin.TrimStart('/'); Journal "commande reçue : $($script:commande)"; Repondre $s '200 OK' 'application/json' ('{"ok":true,"commande":"' + $script:commande + '"}') } }
            else { Repondre $s '404 Not Found' 'application/json' '{"ok":false}' }
        } catch {} finally { $cl.Close() } }
    if (Test-Path (Join-Path $Racine 'ARRET')) { $script:commande = 'arreter' }
    if ($script:commande -eq 'pause') { $script:enPause = $true; $etat.statut = 'pause'; $script:commande = $null }
    elseif ($script:commande -eq 'reprendre') { $script:enPause = $false; $etat.statut = 'actif'; $script:commande = $null } }
function Attendre($ms) { $fin = (Get-Date).AddMilliseconds($ms); while ((Get-Date) -lt $fin) { Servir-Controle; if ($script:commande -eq 'arreter') { return }; Start-Sleep -Milliseconds 100 } }

# ---------------- file et lots
function Consigne($nom) {
    if (-not $consignes.ContainsKey($nom)) { $consignes[$nom] = [IO.File]::ReadAllText((Join-Path $Racine ('consignes\' + $nom + '.txt')), $UTF8).Trim() }
    return $consignes[$nom] }
function Faits($sortie) {
    $f = @{}; if (Test-Path $sortie) { foreach ($l in [IO.File]::ReadAllLines($sortie, $UTF8)) { if ($l.Trim()) { try { $f[($l | ConvertFrom-Json).id] = 1 } catch {} } } }
    return $f }
function Clore-Lot($nom) {
    $c = $lots[$nom].chemin; $d = Join-Path $Racine ('traite\' + [IO.Path]::GetFileName($c))
    if (Test-Path $d) { $d = Join-Path $Racine ('traite\' + (Get-Date).ToString('yyyyMMdd_HHmmss') + '_' + [IO.Path]::GetFileName($c)) }
    Move-Item $c $d; $lots.Remove($nom); Journal "lot $nom terminé" }
function Charger-Lot($chemin, $deja) {
    $nom = [IO.Path]::GetFileNameWithoutExtension($chemin); $dest = Join-Path $Racine ('encours\' + [IO.Path]::GetFileName($chemin))
    if (-not $deja) { Move-Item $chemin $dest }
    $sortie = Join-Path $Racine ('sortie\' + $nom + '_resultats.jsonl'); $faits = Faits $sortie; $arrivee = (Get-Item $dest).LastWriteTime; $n = 0
    foreach ($l in [IO.File]::ReadAllLines($dest, $UTF8)) {
        if (-not $l.Trim()) { continue }
        $t = $l | ConvertFrom-Json; if ($faits.ContainsKey($t.id)) { continue }
        $script:seq++; $p = 2; if ($t.PSObject.Properties['prio']) { $p = [double]$t.prio }
        [void]$file.Add(@{ t = $t; lot = $nom; prio = $p; arrivee = $arrivee; seq = $script:seq; essais = 0 }); $n++ }
    $lots[$nom] = @{ reste = $n; sortie = $sortie; chemin = $dest }; Journal "lot $nom : $n tâche(s)"
    if ($n -eq 0) { Clore-Lot $nom } }
function Choisir {
    $now = Get-Date; $meilleur = $null; $bm = 1e9
    foreach ($x in $file) { $x.eff = $x.prio - ($now - $x.arrivee).TotalMinutes / [double]$C.vieillissement_min
        if ($x.eff -lt $bm -or ($x.eff -eq $bm -and $x.seq -lt $meilleur.seq)) { $bm = $x.eff; $meilleur = $x } }
    if ($etat.modele) {
        $memes = @($file | Where-Object { $_.t.modele -eq $etat.modele -and $_.eff -le $bm + [double]$C.fenetre_modele } | Sort-Object { $_.eff }, { $_.seq })
        if ($memes.Count -gt 0) { return $memes[0] } }
    return $meilleur }

# ---------------- appel à LM Studio (asynchrone : l'API reste joignable et l'arrêt annule l'appel)
$handler = New-Object System.Net.Http.HttpClientHandler; $handler.UseProxy = $false
$client = New-Object System.Net.Http.HttpClient($handler); $client.Timeout = [TimeSpan]::FromSeconds([double]$C.delai_tache_s + 30)
function Corps($t) {
    $type = 'chat'; if ($t.PSObject.Properties['type']) { $type = $t.type }
    if ($type -eq 'embedding') { return @('/v1/embeddings', @{ model = $t.modele; input = $t.u }, $type) }
    $sys = if ($t.PSObject.Properties['consigne']) { Consigne $t.consigne } else { $t.systeme }
    $mx = 40; if ($t.PSObject.Properties['max_tokens']) { $mx = [int]$t.max_tokens }
    $b = @{ model = $t.modele; temperature = 0; max_tokens = $mx; reasoning_effort = 'none'; messages = @(@{ role = 'system'; content = $sys }, @{ role = 'user'; content = $t.u }) }
    if ($t.PSObject.Properties['valeurs']) {
        $b.response_format = @{ type = 'json_schema'; json_schema = @{ name = 'r'; strict = $true; schema = @{ type = 'object'
            properties = @{ r = @{ type = 'string'; enum = @($t.valeurs) } }; required = @('r'); additionalProperties = $false } } } }
    return @('/v1/chat/completions', $b, $type) }
function Appeler($t) {   # renvoie @{ok; r; tokens; erreur; injoignable; annule}
    $chemin, $b, $type = Corps $t
    $cts = New-Object System.Threading.CancellationTokenSource
    $contenu = New-Object System.Net.Http.StringContent(($b | ConvertTo-Json -Depth 12 -Compress), $UTF8, 'application/json')
    $tache = $client.PostAsync($C.url_lmstudio + $chemin, $contenu, $cts.Token); $limite = (Get-Date).AddSeconds([double]$C.delai_tache_s)
    while (-not $tache.IsCompleted) {
        Servir-Controle
        if ($script:commande -eq 'arreter') { $cts.Cancel(); return @{ ok = $false; annule = $true; erreur = 'arrêt demandé' } }
        if ((Get-Date) -gt $limite) { $cts.Cancel(); return @{ ok = $false; erreur = 'délai dépassé' } }
        Start-Sleep -Milliseconds 100 }
    if ($tache.IsFaulted -or $tache.IsCanceled) {
        $m = if ($tache.Exception) { $tache.Exception.GetBaseException().Message } else { 'annulé' }
        return @{ ok = $false; erreur = $m; injoignable = ($m -match 'connect|connexion|refus|actively|Unable|Impossible|No connection') } }
    $rep = $tache.Result; $txt = $UTF8.GetString($rep.Content.ReadAsByteArrayAsync().Result)
    if (-not $rep.IsSuccessStatusCode) { return @{ ok = $false; erreur = "HTTP $([int]$rep.StatusCode) : " + $txt.Substring(0, [Math]::Min(200, $txt.Length)) } }
    $j = $txt | ConvertFrom-Json
    if ($type -eq 'embedding') { return @{ ok = $true; r = $j.data[0].embedding; tokens = $null } }
    $c = $j.choices[0].message.content; $r = $c; try { $r = ($c | ConvertFrom-Json).r } catch {}
    return @{ ok = $true; r = $r; tokens = $j.usage.completion_tokens } }

# ---------------- boucle principale
Journal "démarrage v3 ; file : $Racine ; gestion : http://127.0.0.1:$($C.port)/"
foreach ($f in Get-ChildItem (Join-Path $Racine 'encours') -Filter *.jsonl) { Charger-Lot $f.FullName $true }
$etat.statut = 'actif'; $vuDernier = Get-Date; $perteDepuis = $null; $dernierScan = Get-Date '2000-01-01'; $dernierEtat = $dernierScan; $dernierMem = $dernierScan; $code = 0
while ($true) {
    Servir-Controle
    if ($script:commande -eq 'arreter') { $etat.raison_arret = 'arrêt demandé (API ou fichier ARRET)'; break }
    $now = Get-Date
    if (($now - $dernierScan).TotalSeconds -ge 2) { $dernierScan = $now
        foreach ($f in Get-ChildItem (Join-Path $Racine 'entree') -Filter *.jsonl) {
            if (($now - $f.LastWriteTime).TotalSeconds -lt 3) { continue }
            try { Charger-Lot $f.FullName $false } catch { Journal ("lot illisible " + $f.Name + " : " + $_.Exception.Message) } } }
    if (($now - $dernierEtat).TotalSeconds -ge 5) { Ecrire-Etat; $dernierEtat = $now }
    if ($script:enPause) { Attendre 300; continue }
    if (($now - $dernierMem).TotalSeconds -ge 30) { $dernierMem = $now
        try { $libre = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024
            if ($libre -lt [double]$C.memoire_libre_min_mo) { $etat.statut = "pause mémoire ($([int]$libre) Mo libres)"; Ecrire-Etat; Journal $etat.statut; Attendre 60000; $etat.statut = 'actif'; continue } } catch {} }
    if ($file.Count -eq 0) {
        $etat.statut = 'en attente de tâches'
        if (($now - $vuDernier).TotalMinutes -ge [double]$C.arret_si_inactif_min) { $etat.raison_arret = "file vide depuis $($C.arret_si_inactif_min) min"; $code = 3; break }
        Attendre 1000; continue }
    $vuDernier = $now; $x = Choisir; $file.Remove($x); $t = $x.t
    $etat.statut = 'actif'; $etat.tache_en_cours = @{ id = $t.id; modele = $t.modele; depuis = $now.ToString('s') }
    $t0 = Get-Date; $res = Appeler $t; $ms = [int]((Get-Date) - $t0).TotalMilliseconds; $etat.tache_en_cours = $null
    if ($res.annule) { [void]$file.Add($x); $etat.raison_arret = 'arrêt demandé pendant un appel (tâche remise en file)'; break }
    if ($res.injoignable) {
        [void]$file.Add($x); $etat.lmstudio_joignable = $false
        if (-not $perteDepuis) { $perteDepuis = Get-Date; Journal ('LM Studio injoignable : ' + $res.erreur) }
        if (((Get-Date) - $perteDepuis).TotalMinutes -ge [double]$C.arret_si_lmstudio_absent_min) { $etat.raison_arret = "serveur LM Studio interrompu depuis $($C.arret_si_lmstudio_absent_min) min"; $code = 2; break }
        $etat.statut = 'attente de LM Studio'; Ecrire-Etat; Attendre 10000; continue }
    $perteDepuis = $null; $etat.lmstudio_joignable = $true
    if (-not $res.ok) { $x.essais++; if ($x.essais -lt [int]$C.essais) { [void]$file.Add($x); Attendre (2000 * $x.essais); continue } }
    $ligne = @{ id = $t.id; modele = $t.modele; ms = $ms; essai = $x.essais + 1; fin = (Get-Date).ToString('s') }
    if ($res.ok) { $ligne.r = $res.r; $ligne.tokens = $res.tokens; $etat.traites++ } else { $ligne.erreur = $res.erreur; $etat.erreurs++ }
    [IO.File]::AppendAllText($lots[$x.lot].sortie, (($ligne | ConvertTo-Json -Depth 4 -Compress) + "`n"), $UTF8)
    $etat.modele = $t.modele; $etat.dernier = $t.id
    $lots[$x.lot].reste--; if ($lots[$x.lot].reste -le 0) { Clore-Lot $x.lot; Ecrire-Etat }
    Attendre ([int]$C.pause_entre_taches_ms)
}
$etat.statut = 'arrêté'; $etat.arret = (Get-Date).ToString('s'); Ecrire-Etat; Journal ("arrêt : " + $etat.raison_arret)
try { $L.Stop() } catch {}; try { $client.Dispose() } catch {}
exit $code
