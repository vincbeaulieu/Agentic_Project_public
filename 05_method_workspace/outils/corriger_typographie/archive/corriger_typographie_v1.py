"""
OUTIL: corriger_typographie
VERSION: 1
RESUME: Correctif déterministe de la typographie française dans la vue acceptée d'un rapport Word révisé en suivi (constats DR-04 de detecteurs_rapport) : double espace entre deux mots, espace avant une virgule ou un point, espace manquante avant « ; ? ! » et « : » (caractère d'espace le plus employé du document). Ne touche ni la couverture (premiers paragraphes), ni la table des matières, ni la section Références (titres anglais), ni les URL, DOI, heures, rapports « 1:1 » ou extensions de fichiers. Sortie en opérations « remplacer » pour appliquer_suivi (module POINTS/OPS/REPONSES) et aperçu avant/après ; nouvelle version seulement si le contenu change.
USAGE: python3 outils/corriger_typographie.py <docx> <sortie_dossier> [--detecteurs <constats.json>] [--paragraphes 247,301] [--couverture 24] [--exclure "Références;Bibliographie"] [--prefixe TYPO] [--base ops_typographie]
ENTREES: docx en suivi des modifications ; facultatif : constats de detecteurs_rapport (DR-04) pour choisir les paragraphes (sinon tous)
SORTIES: <sortie>/<base>_vN.py (POINTS, OPS « remplacer » : cible = paraId, couples [(texte accepté, texte corrigé)], REPONSES vide) ; <sortie>/apercu_<base>_vN.md ; résumé ; événement dans journal/
CATEGORIE: revision_rapport
BANC: tests/test_corriger_typographie_v1.py
REMPLACE: -
"""
import sys, os, re, json, zipfile, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from cc_lib_v4 import ecrire_versionne, evenement, importer   # noqa: E402
VERSION = 1
PROTEGE = re.compile(r'https?://\S+|www\.\S+|doi:\s*\S+|\b\d{1,2}:\d{2}\b|\b\d+:\d+\b|\b[\w-]+\.(?:py|xlsx|docx|csv|json|md|txt|pdf|knwf)\b|§[A-Z]?[\d.]+', re.I)


def espace_usuelle(textes):
    """Caractère d'espace le plus employé devant « : » et « ; » dans le document (espace, insécable ou fine insécable)."""
    c = collections.Counter(m.group(1) for t in textes for m in re.finditer(r'(\s)[:;]', t))
    return c.most_common(1)[0][0] if c else ' '


def corriger(texte, esp=' '):
    """Texte corrigé (ou identique). Les zones protégées (URL, DOI, heures, ratios, fichiers, renvois §) ne sont pas modifiées."""
    zones = [(m.start(), m.end()) for m in PROTEGE.finditer(texte)]
    def libre(i): return not any(a <= i < b for a, b in zones)
    out = []; i = 0; n = len(texte)
    while i < n:
        c = texte[i]
        if c == ' ' and libre(i):
            j = i
            while j < n and texte[j] == ' ': j += 1
            g = texte[i - 1] if i else ''; d = texte[j] if j < n else ''
            if d in ',.' and g and (g.isalnum() or g in ')»]') and (j + 1 >= n or texte[j + 1] in '   )»]' or texte[j + 1] == '\n') and not (d == '.' and j + 1 < n and texte[j + 1].isdigit()):
                i = j; continue                                              # espace avant « , » ou « . »
            if j - i >= 2 and g and d and not g.isspace() and not d.isspace() and g != '\t' and d != '\t':
                out.append(' '); i = j; continue                             # double espace entre deux mots
            out.append(texte[i:j]); i = j; continue
        if c in ';?!:' and libre(i) and i and (texte[i - 1].isalpha() or texte[i - 1] in ')»]') and (i + 1 >= n or texte[i + 1] in '   \n'):
            out.append(esp + c); i += 1; continue                            # espace manquante avant la ponctuation haute
        out.append(c); i += 1
    return ''.join(out)


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def main(a):
    if len(a) < 2: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    DR = importer('detecteurs_rapport')
    docx, out = a[:2]; pref = opt(a, '--prefixe', 'TYPO'); base_nom = opt(a, '--base', 'ops_typographie')
    couv = int(opt(a, '--couverture', 24)); exclus = [x.strip().lower() for x in opt(a, '--exclure', 'Références;Bibliographie;References').split(';') if x.strip()]
    P = {p['i']: p for p in DR.vues(zipfile.ZipFile(docx))}
    esp = espace_usuelle(p['acc'] for p in P.values())
    if opt(a, '--paragraphes'): cibles = sorted(int(x) for x in opt(a, '--paragraphes').split(','))
    elif opt(a, '--detecteurs'):
        with open(opt(a, '--detecteurs'), encoding='utf-8') as g: C = json.load(g)['constats']
        cibles = sorted({c['index'] for c in C if c['regle'] == 'DR-04' and c.get('index') is not None})
    else: cibles = sorted(P)
    POINTS, OPS, ap, ecartes = [], [], [f'# Aperçu des corrections typographiques — {os.path.basename(docx)}', ''], []
    for i in cibles:
        p = P.get(i)
        if p is None or not p['acc'].strip(): continue
        if i < couv or p['toc'] or any(p['section'].lower().startswith(x) for x in exclus):
            ecartes.append(f'¶{i} : ' + ('couverture' if i < couv else 'table des matières' if p['toc'] else f'section exclue ({p["section"][:30]})')); continue
        r = corriger(p['acc'], esp)
        if r == p['acc']: continue
        n = len(POINTS) + 1
        POINTS.append(dict(id=f'{pref}-P{n:03d}', sources=[f'DR-04 ¶{i}'], point=f'¶{i} : typographie (espaces) non conforme à la typographie française.',
                           demande='Corriger les espaces sans toucher au texte.', correctif='passe précédente : espaces doublées, manquantes ou en trop.',
                           regle_le_point='non', nouveau_probleme='typographie (DR-04)', statut_rev1_vrai='non', verdict='A_CORRIGER',
                           raison='Correctif déterministe (corriger_typographie) : espaces seulement.', ops=[f'{pref}-M{n:03d}']))
        OPS.append(dict(id=f'{pref}-M{n:03d}', type='remplacer', point=f'{pref}-P{n:03d}', cible=p['pid'], couples=[(p['acc'], r)]))
        ap += [f'## ¶{i} ({p["pid"]}, {p["section"][:60]})', '', f'- Avant : {p["acc"]}', f'- Après : {r}', '']
    ap += ['## Écartés', ''] + [f'- {x}' for x in ecartes] + ['']
    corps = (f'"""Corrections typographiques générées par corriger_typographie v{VERSION} (déterministe) sur {os.path.basename(docx)}."""\n'
             f'POINTS = {POINTS!r}\nOPS = {OPS!r}\nREPONSES = {{}}\n')
    os.makedirs(out, exist_ok=True)
    f1, _ = ecrire_versionne(out, base_nom, 'py', corps); f2, _ = ecrire_versionne(out, 'apercu_' + base_nom, 'md', '\n'.join(ap))
    evenement('corriger_typographie', VERSION, 'corriger', dict(paragraphes=len(cibles), corriges=len(OPS), ecartes=len(ecartes)))
    print(f1); print(f2); print(f'{len(OPS)} paragraphe(s) corrigé(s) sur {len(cibles)} ; {len(ecartes)} écarté(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
