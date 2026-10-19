"""
OUTIL: reparer_fragments
VERSION: 4
RESUME: Correctif déterministe d'un défaut de moteur de révision : des insertions placées en fin de paragraphe au lieu de leur place laissent un trou dans la phrase (« , ; », « ( ) », « les  ( », « et , », « . , », « ; . », « .  et », début de paragraphe vide) et un fragment collé à la fin (« …texteEL », « séparés.Catégorie … », dernière phrase sans ponctuation finale). Pour chaque paragraphe de la vue acceptée : fragments de fin repérés (sigle répété collé, mot collé après un point, dernière phrase sans ponctuation finale), trous repérés par motifs ; réparation seulement si le nombre de fragments égale celui des trous (sinon « à vérifier ») ; sortie en opérations « remplacer » pour appliquer_suivi (module POINTS/OPS/REPONSES) et aperçu avant/après. Généralise le script de travail corriger_terme_v3 (limité à « EL »).
USAGE: python3 outils/reparer_fragments.py <docx> <sortie_dossier> [--detecteurs <constats.json>] [--paragraphes 3,7] [--prefixe DR09F] [--base ops_DR09_fragments]
ENTREES: docx en suivi des modifications ; facultatif : constats de detecteurs_rapport (DR-09) pour choisir les paragraphes (sinon tous les paragraphes à trou)
SORTIES: <sortie>/<base>_vN.py (POINTS, OPS type « remplacer » avec cible = paraId et couples [(texte accepté, texte réparé)], REPONSES) ; <sortie>/apercu_<base>_vN.md ; résumé (réparés, à vérifier) ; événement dans journal/
CATEGORIE: revision_rapport
BANC: tests/test_reparer_fragments_v4.py
REMPLACE: reparer_fragments_v3 (trou après une fin de phrase non reconnu : « par partie.  et la conclusion … » — phrase supprimée, double espace puis minuscule — laissait le fragment de fin en place ; motif ajouté) ; v3 : reparer_fragments_v2 (trou « ponctuation intérieure suivie d'un point » non reconnu : « établi dans ses principes ; . Il décrit » restait « aucun trou » ; motif ajouté pour « ; . », « , . » et « : . ») ; v2 : reparer_fragments_v1 (détecteurs chargés dans leur version courante (cc_lib_v4.importer) et non plus dans une version figée devenue inutilisable après le renommage des dossiers) ; v1 : - (généralise 11_reevaluation/90_scripts/corriger_terme_v3.py)
"""
import sys, os, re, json, zipfile
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
VERSION = 2
MOTS_TROU = r'(?:des|les|la|le|du|aux|au|ces|ses|leurs?|et|ou|de|en|par|sur|pour|avec|dans|entre)'
TROUS = [re.compile(r'[,(](\s*)(?=[;,)])'),                          # « , ; » « ( ) » « , , »  (groupe 1 : position du trou)
         re.compile(r'\.(\s+)(?=[;,])'),                              # « . ; » « . , »
         re.compile(r'[;:,](\s+)(?=\.(?:\s|$))'),                      # « ; . » « , . » « : . » (v3)
         re.compile(r'[.!?](\s{2,})(?=[a-zà-ÿ])'),                       # « .  et les » : phrase vidée, double espace puis minuscule (v4)
         re.compile(r'\((\s+)(?=\S)'),                                 # « ( ou » : parenthèse ouverte suivie d'une espace
         re.compile(r'(?<=[\w\d])( )(?=[,.](?:\s|$))'),                  # espace avant « , » ou « . » après un mot
         re.compile(r'(?<![.!?:;])(\s{2,})(?=\S)'),                    # double espace hors fin de phrase
         re.compile(r'\b' + MOTS_TROU + r'(\s+)(?=[(),.;:»])', re.I),   # « les , » « et , »
         re.compile(r'\b(?:les|des|ces)(\s+)(?=(?:sont|ont|étaient|seront)\b)', re.I)]
FIN = tuple('.!?:;)»]…')
EXCLUS_COLLE = re.compile(r'\.(?:py|xlsx|docx|csv|json|md|txt|pdf|com|org|fr)\b|https?://|www\.|\b(?:e\.g|i\.e|etc|cf|p|n|fig|réf)\.', re.I)


def fragments(acc):
    """(base, [fragments]) : texte sans les fragments de fin, et fragments dans l'ordre où ils doivent être replacés."""
    s = acc.rstrip()
    m = re.search(r'(?<=[a-zà-ÿ.!?)])(([A-Z]{2,5}?)(?:\2)*)$', s)                # sigle répété collé : « …texteEL », « ….ELEL »
    if m and len(m.group(1)) % len(m.group(2)) == 0:
        return s[:m.start()], [m.group(2)] * (len(m.group(1)) // len(m.group(2)))
    colles = [x for x in re.finditer(r'(?<=[a-zà-ÿ0-9)\]»])\.(?=[^\s\d.,;:)\]])', s) if not EXCLUS_COLLE.search(s[max(0, x.start() - 6):x.start() + 6])]
    if colles:
        j = colles[-1].start() + 1; return s[:j], [s[j:].strip()]
    if s and not s.endswith(FIN):                                             # dernière phrase sans ponctuation finale
        b = [x for x in re.finditer(r'[.!?]\s+(?=\S)', s)]
        if b:
            j = b[-1].start() + 1; return s[:j], [s[j:].strip()]
    return s, []


def trous(base):
    pos = sorted({m.start(1) for rx in TROUS for m in rx.finditer(base)})
    if base[:1].isspace() and base.lstrip()[:1].islower(): pos = [0] + pos   # début de paragraphe vide
    out = []
    for p in pos:
        if out and p - out[-1] <= 2: continue
        out.append(p)
    return out


def remplir(base, h, f):
    g, d = base[:h].rstrip(), base[h:].lstrip()
    if not g: f = f[:1].upper() + f[1:]
    sep_g = '' if (not g or g.endswith(('(', '« '))) else ' '
    sep_d = '' if d[:1] in (',', '.', ')', '…') or not d else ' '
    return g + sep_g + f + sep_d + d


def reparer(acc, ori=None):
    """(texte réparé, None) ou (None, raison). Avec ori (vue d'origine du paragraphe), un trou déjà présent dans l'origine
    n'est pas un trou créé par la révision : il est ignoré."""
    base, F = fragments(acc); T = trous(base)
    if ori: T = [h for h in T if base[max(0, h - 12):h + 12] not in ori]
    if not F: return None, 'aucun fragment de fin'
    if not T: return None, 'aucun trou'
    if len(F) != len(T): return None, f'{len(F)} fragment(s) pour {len(T)} trou(s)'
    for h, f in sorted(zip(T, F), reverse=True): base = remplir(base, h, f)
    if not base.rstrip().endswith(FIN) and acc.rstrip().endswith(FIN): return None, 'ponctuation finale perdue'
    return re.sub(r'(?<=\S) {2,}(?=\S)', ' ', base), None


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a else d


def main(a):
    if len(a) < 2: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    from cc_lib_v4 import importer; DR = importer('detecteurs_rapport')
    from cc_lib_v1 import ecrire_versionne, evenement
    docx, out = a[:2]; pref = opt(a, '--prefixe', 'DR09F'); base_nom = opt(a, '--base', 'ops_DR09_fragments')
    P = {p['i']: p for p in DR.vues(zipfile.ZipFile(docx))}
    if opt(a, '--paragraphes'): cibles = sorted(int(x) for x in opt(a, '--paragraphes').split(','))
    elif opt(a, '--detecteurs'):
        with open(opt(a, '--detecteurs'), encoding='utf-8') as g: C = json.load(g)['constats']
        cibles = sorted({c['index'] for c in C if c['regle'] == 'DR-09' and c.get('index') is not None})
    else: cibles = sorted(i for i, p in P.items() if p['acc'].strip() and not p['toc'] and fragments(p['acc'])[1] and trous(fragments(p['acc'])[0]))
    POINTS, OPS, ap, refus = [], [], [f'# Aperçu des réparations de fragments — {os.path.basename(docx)}', ''], []
    for i in cibles:
        p = P[i]; r, raison = reparer(p['acc'], p['ori'])
        if r is None:
            if raison != 'aucun fragment de fin': refus.append(f'¶{i} : {raison}')
            continue
        n = len(POINTS) + 1
        POINTS.append(dict(id=f'{pref}-P{n:03d}', sources=[f'DR-09 ¶{i}'], point=f'¶{i} : fragment inséré en fin de paragraphe au lieu de sa place (trou dans la phrase).',
                           demande='Rendre au texte inséré sa place, sans rien perdre.', correctif='passe précédente : insertion placée en fin de paragraphe.',
                           regle_le_point='non', nouveau_probleme='phrase incomplète et fragment collé dans la vue acceptée', statut_rev1_vrai='non', verdict='A_CORRIGER',
                           raison='Correctif déterministe (reparer_fragments) : fragment(s) de fin replacé(s) dans le(s) trou(s), en nombre égal.', ops=[f'{pref}-M{n:03d}']))
        OPS.append(dict(id=f'{pref}-M{n:03d}', type='remplacer', point=f'{pref}-P{n:03d}', cible=p['pid'], couples=[(p['acc'], r)]))
        ap += [f'## ¶{i} ({p["pid"]}, {p["section"][:60]})', '', f'- Avant : {p["acc"]}', f'- Après : {r}', '']
    ap += ['## À vérifier', ''] + [f'- {x}' for x in refus] + ['']
    corps = (f'"""Réparations de fragments déplacés, générées par reparer_fragments v{VERSION} (déterministe) sur {os.path.basename(docx)}."""\n'
             f'POINTS = {POINTS!r}\nOPS = {OPS!r}\nREPONSES = {{}}\n')
    f1, _ = ecrire_versionne(out, base_nom, 'py', corps); f2, _ = ecrire_versionne(out, 'apercu_' + base_nom, 'md', '\n'.join(ap))
    evenement('reparer_fragments', VERSION, 'reparer', dict(paragraphes=len(cibles), repares=len(OPS), a_verifier=len(refus)))
    print(f1); print(f2); print(f'{len(OPS)} réparé(s) sur {len(cibles)} paragraphe(s) ; {len(refus)} à vérifier'); [print('  ', x) for x in refus]
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
