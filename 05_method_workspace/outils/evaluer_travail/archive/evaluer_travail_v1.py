"""
OUTIL: evaluer_travail
VERSION: 1
RESUME: Évaluateur déterministe par défaut de tout dossier de travail et de ses livrables : organisation (O), intégrité et non-écrasement (E), nommage et versions (N), commentaires Claude (K), livrables Word (D), leçon L3. Score d'alignement pondéré, verdict, manifeste d'empreintes horodaté.
USAGE: python3 evaluer_travail_v1.py <dossier_de_travail> [--json <constats.json>] [--sans-xsd] [--sans-manifeste] [--regles R1,R2]
ENTREES: dossier NN_sujet (TRAVAIL_vN.json pour les contrôles D et L3)
SORTIES: résumé ; 95_journal/evaluations/evaluation_<ts>.json ; 95_journal/manifestes/manifeste_<ts>.json ; événement dans journal/ ; --json : {"constats": [{"regle", "chemin", "detail"}]}
CATEGORIE: evaluation
BANC: bancs/evaluer_travail/
REMPLACE: -
"""
import sys, os, re, json, time, stat, zipfile, subprocess, datetime, collections
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import h16, analyser_nom, est_exempt, evenement, RE_SANS_ACCENT, version_tuple, RACINE_CC
import docx_couches_v1 as dc

OUTIL, VERSION = 'evaluer_travail', 1
REGLES = json.load(open(os.path.join(RACINE_CC, 'regles', 'regles_travail_v1.json'), encoding='utf-8'))['regles']
GRAV = {r['id']: r['gravite'] for r in REGLES}
POIDS = {'bloquant': 3, 'majeur': 2, 'mineur': 1}
VALIDATE = '/mnt/skills/public/docx/scripts/office/validate.py'
PREFIXES = ('Fait :', 'Proposition :', 'Données :', 'Question :', 'Non retenu :', 'Conforme :', '[Correction', '[Réévaluation')
SOUS_PERMIS = re.compile(r'^(00_sources|(0[1-9]|[1-8]\d)_[a-z0-9_.\-]+|90_scripts|95_journal|98_livrables|99_livrables_modifiables)$')
NON_SUIVIS = re.compile(r'(^|/)(__pycache__|\.config|\.cache|_profil[^/]*)(/|$)')


def lister(d):
    out = []
    for r, ds, fs in os.walk(d):
        ds.sort()
        for f in sorted(fs):
            rel = os.path.relpath(os.path.join(r, f), d).replace('\\', '/')
            if NON_SUIVIS.search(rel): continue
            out.append(rel)
    return out


def derniere(d, rx):
    if not os.path.isdir(d): return None
    c = sorted((version_tuple(m.group(1)), f) for f in os.listdir(d) for m in [re.match(rx, f)] if m)
    return os.path.join(d, c[-1][1]) if c else None


def main():
    a = sys.argv[1:]
    d = os.path.abspath(a[0]); opt = set(x for x in a if x.startswith('--'))
    jout = a[a.index('--json') + 1] if '--json' in a else None
    seules = set(a[a.index('--regles') + 1].split(',')) if '--regles' in a else None
    t0 = time.time(); c0 = time.process_time()
    C = []   # constats
    def constat(regle, chemin, detail=''):
        if seules is None or regle in seules: C.append(dict(regle=regle, chemin=chemin, detail=detail))
    nom_dossier = os.path.basename(d.rstrip('/'))
    fichiers = lister(d)
    lus = 0
    # ---------- O
    if not re.match(r'^(0[1-9]|[1-9]\d)_[a-z0-9_.\-]+$', nom_dossier): constat('O1', nom_dossier)
    for s in ('00_sources', '95_journal', '98_livrables', '99_livrables_modifiables'):
        if not os.path.isdir(os.path.join(d, s)): constat('O2', s, 'manquant')
    for s in sorted(os.listdir(d)):
        if os.path.isdir(os.path.join(d, s)) and not SOUS_PERMIS.match(s): constat('O3', s)
        if os.path.isfile(os.path.join(d, s)) and not re.match(r'^(LISEZMOI_v\d+(\.\d+)*\.md|TRAVAIL_v\d+\.json)$', s): constat('O4', s)
    ftrav = derniere(d, r'^TRAVAIL_v(\d+)\.json$')
    TRAV = {}
    if not ftrav: constat('O5', 'TRAVAIL_vN.json', 'absent')
    else:
        try:
            TRAV = json.load(open(ftrav, encoding='utf-8'))
            for k in ('sujet', 'source', 'auteur_revisions', 'version_cible', 'couverture', 'auteurs_relecteurs'):
                if k not in TRAV: constat('O5', os.path.basename(ftrav), f'champ {k} manquant')
        except Exception as e: constat('O5', os.path.basename(ftrav), f'illisible : {e}')
    if not derniere(d, r'^LISEZMOI_v(\d+(?:\.\d+)*)\.md$'): constat('O6', 'LISEZMOI_vN.md', 'absent')
    # ---------- E1, E2
    src = os.path.join(d, '00_sources')
    if os.path.isdir(src):
        fsha = derniere(src, r'^sha256_sources_v(\d+)\.txt$')
        connus = {}
        if not fsha: constat('E1', '00_sources', 'sha256_sources_vN.txt absent')
        else:
            for l in open(fsha, encoding='utf-8'):
                p = l.strip().split(None, 1)
                if len(p) == 2: connus[os.path.basename(p[1].strip().lstrip('*'))] = p[0]
        for rel in fichiers:
            if not rel.startswith('00_sources/') or re.match(r'^00_sources/sha256_sources_v\d+\.txt$', rel): continue
            ch = os.path.join(d, rel); b = os.path.basename(rel)
            if fsha:
                if b not in connus: constat('E1', rel, 'absent du fichier d’empreintes')
                else:
                    import hashlib
                    hh = hashlib.sha256(open(ch, 'rb').read()).hexdigest(); lus += os.path.getsize(ch)
                    if hh[:len(connus[b])] != connus[b] and hh != connus[b]: constat('E1', rel, 'empreinte changée')
            if os.stat(ch).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH): constat('E2', rel, 'inscriptible')
    # ---------- E3, E4
    liv, mod = os.path.join(d, '98_livrables'), os.path.join(d, '99_livrables_modifiables')
    livs = [f for f in fichiers if f.startswith('98_livrables/') and not re.match(r'^98_livrables/empreintes_livrables_v[\d.]+\.txt$', f)]
    if livs:
        femp = derniere(liv, r'^empreintes_livrables_v(\d+(?:\.\d+)*)\.txt$')
        emp = {}
        if not femp: constat('E3', '98_livrables', 'empreintes_livrables_vM.0.0.txt absent')
        else:
            for l in open(femp, encoding='utf-8'):
                p = l.strip().split(None, 1)
                if len(p) == 2: emp[p[1].strip()] = p[0]
        for rel in livs:
            ch = os.path.join(d, rel); b = rel[len('98_livrables/'):]
            if femp:
                if b not in emp: constat('E3', rel, 'absent des empreintes')
                elif h16(ch) != emp[b][:16]: constat('E3', rel, 'empreinte changée')
            if os.stat(ch).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH): constat('E3', rel, 'inscriptible')
            if not os.path.exists(os.path.join(mod, b)): constat('E4', rel, 'copie modifiable absente')
    # ---------- E5 (manifeste)
    mdir = os.path.join(d, '95_journal', 'manifestes')
    prec = derniere(mdir, r'^manifeste_(\d{8}_\d{6})\.json$') if os.path.isdir(mdir) else None
    manif = {}
    for rel in fichiers:
        if rel.startswith('95_journal/manifestes/') or rel.startswith('95_journal/evaluations/'): continue
        ch = os.path.join(d, rel); manif[rel] = [h16(ch), os.path.getsize(ch)]; lus += os.path.getsize(ch)
    if prec:
        old = json.load(open(prec, encoding='utf-8'))['fichiers']
        for rel, (hh, taille) in old.items():
            if rel not in manif: constat('E5', rel, 'disparu depuis ' + os.path.basename(prec))
            elif manif[rel][0] != hh:
                ch = os.path.join(d, rel)
                ajout = False
                try:
                    if os.path.getsize(ch) > taille:
                        import hashlib
                        with open(ch, 'rb') as f: debut = f.read(taille)
                        ajout = hashlib.sha256(debut).hexdigest()[:16] == hh
                except Exception: pass
                if not ajout: constat('E5', rel, 'contenu changé (écrasement)')
    # ---------- N
    vus = collections.defaultdict(set)
    for rel in fichiers:
        b = os.path.basename(rel)
        if rel.startswith('95_journal/manifestes/') or rel.startswith('95_journal/evaluations/'): continue
        if est_exempt(rel): continue
        if not RE_SANS_ACCENT.match(b): constat('N2', rel)
        info = analyser_nom(b)
        if info is None: constat('N1', rel, 'sans version'); continue
        vus[(info['nom'], info['ver'], info.get('qui'), info.get('variante'), info['ext'])].add(manif.get(rel, [None])[0])
        if rel.startswith(('98_livrables/', '99_livrables_modifiables/')):
            vc = str(TRAV.get('version_cible', ''))
            if info['forme'] != 'semver' or not re.match(r'^\d+\.0\.0$', info['ver']) or info.get('qui'):
                constat('N3', rel, f'version {info["ver"]}{info.get("qui") or ""} (attendu M.0.0)')
            elif vc and info['ver'] != vc: constat('N3', rel, f'version {info["ver"]} ≠ version_cible {vc}')
        elif info['forme'] == 'semver' and info.get('qui') is None and not info['ver'].endswith('.0.0') and info['ext'] in ('docx', 'xlsx', 'pptx', 'pdf'):
            constat('N4', rel, f'révision {info["ver"]} sans a/c')
    for k, hs in vus.items():
        if len(hs) > 1: constat('N5', f'{k[0]}_v{k[1]}{k[2] or ""}{"_" + k[3] if k[3] else ""}.{k[4]}', f'{len(hs)} contenus différents')
    # ---------- K, D, L3 (livrables Word)
    auteur = TRAV.get('auteur_revisions'); source = os.path.join(d, TRAV['source']) if TRAV.get('source') else None
    relect = set(TRAV.get('auteurs_relecteurs', []))
    couv = TRAV.get('couverture')
    for rel in livs:
        if not rel.endswith('.docx'): continue
        ch = os.path.join(d, rel); info = analyser_nom(os.path.basename(rel)) or {}
        lecture = (info.get('variante') or '').startswith('lecture')
        if '--sans-xsd' not in opt and os.path.exists(VALIDATE):
            args = [sys.executable, VALIDATE, ch] + ([] if lecture or not source else ['--original', source, '--author', auteur or ''])
            r = subprocess.run(args, capture_output=True, text=True)
            if 'PASSED' not in r.stdout: constat('D1', rel, r.stdout.strip()[-300:])
        if lecture: continue
        com = dc.commentaires(ch)
        claude = {k: v for k, v in com.items() if 'Claude' in (v['auteur'] or '')}
        if source and os.path.exists(source):
            csrc = dc.commentaires(source)
            for k, v in csrc.items():
                if k not in com or com[k]['texte'] != v['texte'] or com[k]['auteur'] != v['auteur']: constat('D2', rel, f'commentaire {k} absent ou modifié')
            nouveaux = {k: v for k, v in claude.items() if k not in csrc}
        else:
            nouveaux = claude
        for k, v in nouveaux.items():
            t = v['texte'].strip()
            if len(t) > 400 or not t.startswith(PREFIXES): constat('K1', rel, f'commentaire {k} ({len(t)} car.) : {t[:60]!r}')
        par_fil = collections.Counter((v['racine'], v['auteur']) for v in nouveaux.values())
        for (r_, a_), n in par_fil.items():
            if n > 1: constat('K2', rel, f'{n} réponses de {a_} dans le fil {r_}')
        if source and os.path.exists(source) and auteur:
            n_, ec = dc.comparer_refus(ch, auteur, source)
            if ec: constat('D3', rel, f'{len(ec)} paragraphes en écart, ex. {ec[:5]}')
            rs, ro = dc.revisions_par_auteur(source), dc.revisions_par_auteur(ch)
            nouv_aut = {a_ for (_, a_) in ro} - {a_ for (_, a_) in rs}
            if nouv_aut - {auteur}: constat('D5', rel, f'auteurs nouveaux {sorted(nouv_aut)}')
            for (t_, a_), n in rs.items():
                if a_ in relect and ro.get((t_, a_), 0) < n: constat('L3', rel, f'{t_} de {a_} : {ro.get((t_, a_), 0)} / {n} (révisions de relecteur acceptées ou retirées)')
            if couv:
                import zipfile as zf
                from lxml import etree
                A = dc.couches(etree.fromstring(zf.ZipFile(ch).read('word/document.xml')))
                B = dc.couches(etree.fromstring(zf.ZipFile(source).read('word/document.xml')))
                lo, hi = couv
                if A[lo:hi + 1] != B[lo:hi + 1]: constat('D4', rel, f'couverture ¶{lo}-{hi} modifiée')
    # ---------- score et sorties
    appl = [r['id'] for r in REGLES if seules is None or r['id'] in seules]
    en_ecart = sorted({c['regle'] for c in C})
    total = sum(POIDS[GRAV[i]] for i in appl); perdu = sum(POIDS[GRAV[i]] for i in en_ecart if i in GRAV)
    bloq = [i for i in en_ecart if GRAV.get(i) in ('bloquant', 'majeur')]
    res = dict(outil=OUTIL, version=VERSION, dossier=d, date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               verdict='CONFORME' if not bloq else 'NON CONFORME', alignement=round(1 - perdu / total, 4) if total else 1.0,
               regles_en_ecart=en_ecart, constats=C,
               mesures=dict(duree_s=round(time.time() - t0, 3), cpu_s=round(time.process_time() - c0, 3), fichiers=len(fichiers), octets_lus=lus))
    if '--sans-manifeste' not in opt:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')
        os.makedirs(mdir, exist_ok=True)
        with open(os.path.join(mdir, f'manifeste_{ts}.json'), 'x', encoding='utf-8') as f:
            json.dump(dict(date=res['date'], fichiers=manif), f, ensure_ascii=False, indent=0, sort_keys=True)
        edir = os.path.join(d, '95_journal', 'evaluations'); os.makedirs(edir, exist_ok=True)
        with open(os.path.join(edir, f'evaluation_{ts}.json'), 'x', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    if jout:
        with open(jout, 'x', encoding='utf-8') as f: json.dump(dict(constats=[dict(regle=c['regle'], chemin=c['chemin']) for c in C]), f, ensure_ascii=False, indent=1, sort_keys=True)
    evenement(OUTIL, VERSION, 'evaluation', dict(dossier=nom_dossier, verdict=res['verdict'], alignement=res['alignement'],
                                                 regles_en_ecart=en_ecart, n_constats=len(C), mesures=res['mesures']))
    print(f"{res['verdict']} — alignement {res['alignement']:.1%} — {len(C)} constat(s) — règles en écart : {', '.join(en_ecart) or 'aucune'}")
    par = collections.Counter(c['regle'] for c in C)
    for i in en_ecart:
        ex = [c for c in C if c['regle'] == i][:4]
        print(f"  {i} ({GRAV.get(i)}) ×{par[i]} : " + ' ; '.join(f"{c['chemin']}{' — ' + c['detail'] if c['detail'] else ''}" for c in ex))
    return 0 if not bloq else 1


if __name__ == '__main__':
    sys.exit(main())
