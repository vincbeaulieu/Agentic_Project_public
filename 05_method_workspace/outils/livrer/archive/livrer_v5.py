"""
OUTIL: livrer
VERSION: 5
RESUME: Remise d'un livrable par construction conforme : copie chaque fichier dans 98_livrables sous le nom <Nom>_v<version>[_variante].<ext> (version = version_cible de TRAVAIL, égale à la version attendue : décision de l'utilisateur pour ce document, sinon v(X+1).0.0), en lecture seule, ajoute son empreinte à empreintes_livrables_v<version>.txt et sa copie modifiable dans 99_livrables_modifiables ; refuse tout nom existant ; lance ensuite evaluer_travail. v4 : tout docx passe d'abord une porte de livraison, et rien n'est remis si une porte échoue : validation XSD absolue (valider_xsd), ouverture réelle et rendu des pages (rendre_docx), pages déclarées regardées (--pages-vues), images déclarées regardées (--images-vues), mise en forme identique à celle du document de référence (controler_mise_en_forme reference, --reference), aucun nom protégé dans un document annexe (detecter_noms). La fiche de la porte est écrite dans 95_journal/portes/. Procédure (pilote des trois niveaux) : elle n'a pas de logique propre et appelle les outils de base par leur raccourci.
CATALOGUE CONSULTÉ : « livraison docx porte » → livrer (étendu) ; portes reprises du script de projet porte_livraison_v1 (dossier 17), retiré ; valider_xsd, rendre_docx, controler_mise_en_forme reference, detecter_noms : outils de base existants.
USAGE: python3 outils/livrer.py <dossier_de_travail> <fichier>:<Nom>[:<variante>] [...] [--sans-evaluation] [--reference <document de référence.docx> | --sans-reference "<motif>"] [--pages-vues 1,2,5] [--images-vues N] [--porte-seule]
ENTREES: fichiers produits dans les étapes du dossier ; TRAVAIL_vN.json (version_cible, source) ; pour un docx : le document de référence de mise en forme (le rapport qu'il accompagne)
SORTIES: 98_livrables/…, 99_livrables_modifiables/…, empreintes ; 95_journal/portes/porte_<Nom>_<ts>.md et son dossier de rendu ; verdict de evaluer_travail ; événement dans journal/ ; code 0, 1 (porte non conforme : rien n'est remis), 2 (appel invalide)
CATEGORIE: organisation
BANC: tests/test_livrer_v5.py
REMPLACE: livrer_v4 (la version de TRAVAIL_vN.json était lue sur le chemin complet : dans un dossier dont le nom contient « _vN » (17_comparaison_v6.0.4), toutes les fiches avaient la même clé et la v1 pouvait être prise pour la dernière ; le 18 oct. 2026, refus de la remise v2.0.0 décidée par l'utilisateur ; lue désormais sur le nom du fichier) ; v4 : livrer_v3 (un docx était remis sans ouverture réelle, sans pages ni images regardées et sans comparaison de sa mise en forme au rapport : journaux livrés en Calibri 9,5 pt et titres bleus le 16 oct. 2026, erreur 6 du tableau de bord ; les contrôles étaient faits à la main ou par un script de projet) ; v3 : livrer_v2 (version vérifiée avant la remise : version_cible de TRAVAIL = version attendue — règle ou décision de l'utilisateur propre au document, consignée dans TRAVAIL « decision_version », sinon v(X+1).0.0 — par cc_lib_v3.version_attendue ; v2 exigeait M.0.0 et acceptait toute valeur de version_cible) ; v2 : livrer_v1 (lance la version courante de evaluer_travail d'après le registre, au lieu de evaluer_travail_v1 figé)
"""
import sys, os, re, json, shutil, stat, subprocess, glob, zipfile, datetime
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
OUTILS = O
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from cc_lib_v3 import version_attendue, analyser_nom          # noqa: E402
from cc_lib_v1 import h16, version_tuple                      # noqa: E402
from cc_lib_v5 import evenement                               # noqa: E402

OUTIL, VERSION = 'livrer', 4
USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def raccourci(outil, *args, timeout=175):
    """Appel d'un outil de base par son raccourci : toujours la version en service."""
    r = subprocess.run([sys.executable, os.path.join(OUTILS, f'{outil}.py'), *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def opt(a, k):
    if k not in a: return None
    i = a.index(k)
    if i + 1 >= len(a) or a[i + 1].startswith('--'): raise SystemExit(f'appel invalide : {k} sans valeur')
    v = a[i + 1]; del a[i:i + 2]; return v


def porte_docx(d, f, nom, ref, sans_ref, pages_vues, images_vues, annexe, seule=False):
    """Contrôles d'un docx avant remise ; rend (conforme, lignes de la fiche, dossier de la porte)."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')
    P = os.path.join(d, '95_journal', 'portes', f'porte_{nom}_{ts}'); os.makedirs(os.path.dirname(P), exist_ok=True)
    while os.path.exists(P): P += '_b'
    os.makedirs(P); R = []
    c, o = raccourci('valider_xsd', f, '--paquets', os.path.join(P, 'xsd_paquets'))
    R.append(('Validation XSD absolue (valider_xsd)', c == 0, o.splitlines()[0][:200] if o else '—'))
    c, o = raccourci('rendre_docx', f, '--sortie', os.path.join(P, 'rendu'))
    pages = 0
    if c == 0:
        with open(os.path.join(P, 'rendu', 'rendu_v1.json'), encoding='utf-8') as g: rendu = json.load(g)
        pages, n_img = rendu['pages'], len(rendu['images'])
    else: n_img = len([x for x in zipfile.ZipFile(f).namelist() if x.startswith('word/media/')]) if zipfile.is_zipfile(f) else 0
    R.append(('Ouverture réelle par LibreOffice et rendu (rendre_docx)', c == 0 and pages > 0, (o.splitlines()[-1][:200] if o else '—')))
    vues = sorted({int(x) for x in (pages_vues or '').split(',') if x.strip().isdigit()})
    R.append(('Pages regardées (--pages-vues)', (None if seule and not vues else bool(vues) and pages > 0 and all(1 <= v <= pages for v in vues)),
              f'{len(vues)} page(s) déclarée(s) sur {pages} : {vues}' if vues else f'aucune page déclarée regardée ; rendus dans {os.path.relpath(os.path.join(P, "rendu"), d)}'))
    R.append(('Images regardées (--images-vues)', (None if seule and images_vues is None and n_img else n_img == 0 or (images_vues or 0) >= n_img),
              f'{n_img} image(s) ; {images_vues or 0} déclarée(s) regardée(s)' + (f' ; extraites dans {os.path.relpath(os.path.join(P, "rendu", "images"), d)}' if n_img else '')))
    if ref:
        c, o = raccourci('controler_mise_en_forme', 'reference', ref, f, '--json', os.path.join(P, 'format_v1.json'))
        R.append((f'Mise en forme identique à la référence {os.path.basename(ref)} (controler_mise_en_forme reference)', c == 0, o.splitlines()[0][:200] if o else '—'))
    else:
        R.append(('Mise en forme face à une référence', True, f'sans référence, motif déclaré : « {sans_ref} »'))
    if annexe:
        c, o = raccourci('detecter_noms', f)
        R.append(('Aucun nom protégé (detecter_noms, document annexe)', c == 0, o.splitlines()[-1][:200] if o else '—'))
    ok = all(r[1] is not False for r in R)          # None : point de contrôle humain à faire (--porte-seule)
    L = [f'# Porte de livraison : {os.path.basename(f)} → {nom}', '', f'Date : {ts} (UTC) ; verdict : **{"CONFORME" if ok else "NON CONFORME"}**', '',
         '| Contrôle | Résultat | Détail |', '|---|---|---|'] + [f'| {a} | {"à faire (regarder les rendus)" if b is None else "conforme" if b else "**non conforme**"} | {c_} |' for a, b, c_ in R]
    with open(P + '.md', 'x', encoding='utf-8') as g: g.write('\n'.join(L) + '\n')
    return ok, L, P


def main():
    a = sys.argv[1:]
    try:
        ref, sans_ref, pages_vues = opt(a, '--reference'), opt(a, '--sans-reference'), opt(a, '--pages-vues')
        iv = opt(a, '--images-vues'); images_vues = int(iv) if iv is not None else None
    except (SystemExit, ValueError) as e: print(e, '\n' + USAGE); return 2
    seule = '--porte-seule' in a; a = [x for x in a if x != '--porte-seule']
    if not a: print(USAGE); return 2
    d = os.path.abspath(a[0])
    ft = sorted(glob.glob(os.path.join(d, 'TRAVAIL_v*.json')), key=lambda f: version_tuple(re.search(r'^TRAVAIL_v(\d+)\.json$', os.path.basename(f)).group(1)))
    if not ft: raise SystemExit('TRAVAIL_vN.json absent : créer le dossier avec creer_travail_v1.py')
    T = json.load(open(ft[-1], encoding='utf-8')); M = str(T['version_cible']); att, origine = version_attendue(T)
    if att is None and not re.match(r'^\d+\.0\.0$', M): raise SystemExit(f'version_cible {M} : source illisible, attendu M.0.0')
    if att is not None and M != att: raise SystemExit(f'version_cible {M} ≠ {att} attendue ({origine}) : corriger TRAVAIL (nouvelle version) avant la remise')
    specs = []
    for spec in [x for x in a[1:] if not x.startswith('--')]:
        parts = spec.split(':'); f, nom = parts[0], parts[1]; var = parts[2] if len(parts) > 2 else None
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9_\-]*$', nom): raise SystemExit(f'nom {nom!r} : lettres, chiffres, _ et - seulement')
        specs.append((f, nom, var, os.path.splitext(f)[1].lstrip('.')))
    docx = [s for s in specs if s[3] == 'docx']
    if docx and not ref and not sans_ref:
        print('appel invalide : un docx est remis sans document de référence de mise en forme ; donner --reference <rapport.docx>, ou --sans-reference "<motif>"'); return 2
    if ref and not os.path.isfile(ref): print(f'appel invalide : référence introuvable : {ref}'); return 2
    nom_src = (analyser_nom(os.path.basename(T['source'])) or {}).get('nom') if T.get('source') else None
    echec = []
    for f, nom, var, ext in docx:
        annexe = not nom_src or (analyser_nom(os.path.basename(f)) or {}).get('nom') != nom_src
        ok, L, P = porte_docx(d, f, nom, ref, sans_ref, pages_vues, images_vues, annexe, seule)
        print('\n'.join(L)); print(f'fiche : {os.path.relpath(P, d)}.md')
        if not ok: echec.append(nom)
    evenement(OUTIL, VERSION, 'porte', dict(dossier=os.path.basename(d), docx=len(docx), echecs=echec, porte_seule=seule))
    if echec: print(f'NON CONFORME : rien n\'est remis ({", ".join(echec)})'); return 1
    if seule: print('porte seule : rien n\'est remis ; regarder les rendus, puis relancer avec --pages-vues et --images-vues'); return 0
    liv, mod = os.path.join(d, '98_livrables'), os.path.join(d, '99_livrables_modifiables')
    os.makedirs(liv, exist_ok=True); os.makedirs(mod, exist_ok=True)
    femp = os.path.join(liv, f'empreintes_livrables_v{M}.txt')
    lignes = open(femp, encoding='utf-8').read().splitlines() if os.path.exists(femp) else []
    remis = []
    for f, nom, var, ext in specs:
        cible = f"{nom}_v{M}{'_' + var if var else ''}.{ext}"
        for dd in (liv, mod):
            if os.path.exists(os.path.join(dd, cible)): raise SystemExit(f'existe déjà : {os.path.join(dd, cible)} (jamais d’écrasement : monter la version cible)')
        shutil.copy2(f, os.path.join(liv, cible)); shutil.copy2(f, os.path.join(mod, cible))
        os.chmod(os.path.join(liv, cible), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        lignes.append(f'{h16(os.path.join(liv, cible))} {cible}'); remis.append(cible)
    if os.path.exists(femp):
        os.chmod(femp, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        ancien = open(femp, encoding='utf-8').read(); nouveau = '\n'.join(lignes) + '\n'
        assert nouveau.startswith(ancien), 'empreintes : ajout seul'
        open(femp, 'w', encoding='utf-8').write(nouveau)
    else:
        open(femp, 'x', encoding='utf-8').write('\n'.join(lignes) + '\n')
    evenement(OUTIL, VERSION, 'remise', dict(dossier=os.path.basename(d), version=M, fichiers=remis))
    print('remis :', ', '.join(remis))
    if '--sans-evaluation' not in a:
        return subprocess.run([sys.executable, os.path.join(OUTILS, 'evaluer_travail.py'), d]).returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
