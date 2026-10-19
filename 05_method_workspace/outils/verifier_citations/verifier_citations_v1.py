"""
OUTIL: verifier_citations
VERSION: 1
RESUME: Vérifie les preuves d'un ou plusieurs fichiers de jugements contre un texte de référence (une ligne par paragraphe : paraId \t T \t section \t texte, tabulations du texte comprises) : chaque citation « … » (¶paraId) des champs preuve et motif doit se trouver dans son paragraphe (« … » saute une partie, les morceaux dans l'ordre ; guillemets imbriqués admis ; espaces insécables ramenées à une espace) ; chaque terme d'« absent » doit avoir 0 occurrence dans tout le texte (sans casse ; un terme qui commence par « (? » est une expression régulière) ; « verif_image » compte comme preuve si le fichier existe sous --racine ; « verif_hors_texte » est listé à part. Un jugement dont le verdict n'est pas « non traité » doit avoir au moins une preuve vérifiée.
CATALOGUE CONSULTÉ : « citation preuve paragraphe » → aucun outil ; promotion du script de projet 17_comparaison_v6.0.4/90_scripts/verifier_citations_v6.py (v1 à v6 dans ce dossier : guillemets imbriqués, tabulations, absences en regex, images, preuves hors texte).
USAGE: python3 outils/verifier_citations.py <texte_reference.txt> <jugements.json> [<jugements2.json> …] [--racine <dossier des images>] [--json <sortie.json>]
ENTREES: texte de référence ; fichiers de jugements (liste JSON d'objets {fil, verdict, preuve, motif, absent?, verif_image?, verif_hors_texte?}) ; verdicts permis : traité, partiellement traité, non traité, sans objet, décision de l'utilisateur
SORTIES: une ligne par preuve en échec, puis le bilan ; JSON facultatif (jamais écrasé) ; événement dans le journal ; code 0 (conforme), 1 (preuve en échec ou verdict hors liste), 2 (jugement sans preuve vérifiée, ou appel invalide)
CATEGORIE: verification
BANC: tests/test_verifier_citations_v1.py
REMPLACE: - (script de projet verifier_citations_v6 du dossier 17, non promu ; ses versions v1 à v5 y restent)
"""
import sys, os, re, json
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from cc_lib_v5 import evenement                                         # noqa: E402

OUTIL, VERSION = 'verifier_citations', 1
USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()
VERDICTS = {'traité', 'partiellement traité', 'non traité', 'sans objet', "décision de l'utilisateur"}
SUITE = re.compile(r'\s*\((?:[^()¶]*?)¶([0-9A-F]{8})')


def citations(s):
    """[(citation, paraId)] : la citation va du « ouvrant au » qui le referme (guillemets imbriqués admis), suivie de (… ¶paraId)."""
    pile, res = [], []
    for i, ch in enumerate(s):
        if ch == '«': pile.append(i)
        elif ch == '»' and pile:
            d = pile.pop()
            if not pile:
                m = SUITE.match(s, i + 1)
                if m: res.append((s[d + 1:i].strip(), m.group(1)))
    return res


def norm(s):
    return re.sub(r'[    ]+', ' ', s).strip()


def lire_reference(fref):
    T = {}
    for l in open(fref, encoding='utf-8'):
        c = l.rstrip('\n').split('\t')
        if len(c) >= 4: T[c[0]] = norm(' '.join(c[3:]))
    return T


def verifier(T, jugements, racine='.'):
    """Retourne (bilan, lignes d'échec)."""
    TEXTE = '\n'.join(T.values()); TOUT = TEXTE.lower()
    b = dict(conformes=0, echecs=0, sans_preuve=[], hors_texte=[], verdicts_hors_liste=[])
    lignes = []
    for nom, J in jugements:
        for j in J:
            if j.get('verdict') not in VERDICTS: b['verdicts_hors_liste'].append([nom, j.get('fil'), j.get('verdict')])
            n = 0
            for champ in ('preuve', 'motif'):
                for cit, pid in citations(j.get(champ, '') or ''):
                    cit = norm(cit); txt = T.get(pid)
                    bon = txt is not None; pos = 0
                    for x in ([y.strip() for y in cit.split('…') if y.strip()] if bon else []):
                        k = txt.find(x, pos)
                        if k < 0: bon = False; break
                        pos = k + len(x)
                    if bon: b['conformes'] += 1; n += champ == 'preuve'
                    else:
                        b['echecs'] += 1
                        lignes.append(f'ÉCHEC {nom} fil {j.get("fil")} [{champ}] ¶{pid} ' + ('(paraId absent) ' if txt is None else '') + f'« {cit[:120]} »')
            for terme in j.get('absent', []) or []:
                k = len(re.findall(terme, TEXTE, re.I)) if terme.startswith('(?') else TOUT.count(norm(terme).lower())
                if k == 0: b['conformes'] += 1; n += 1
                else: b['echecs'] += 1; lignes.append(f'ÉCHEC {nom} fil {j.get("fil")} [absent] « {terme} » : {k} occurrence(s)')
            im = j.get('verif_image')
            if im:
                if os.path.isfile(os.path.join(racine, im)): b['conformes'] += 1; n += 1
                else: b['echecs'] += 1; lignes.append(f'ÉCHEC {nom} fil {j.get("fil")} [verif_image] fichier absent : {im}')
            if n == 0 and (j.get('verif_hors_texte') or '').strip(): b['hors_texte'].append(j.get('fil')); continue
            if n == 0 and j.get('verdict') != 'non traité': b['sans_preuve'].append(j.get('fil'))
    return b, lignes


def main(a=None):
    a = list(sys.argv[1:] if a is None else a)
    def opt(k):
        if k not in a: return None
        i = a.index(k)
        if i + 1 >= len(a): raise SystemExit(f'appel invalide : {k} sans valeur')
        v = a[i + 1]; del a[i:i + 2]; return v
    try: racine = opt('--racine') or '.'; fjson = opt('--json')
    except SystemExit as e: print(e); print('USAGE:', USAGE); return 2
    if len(a) < 2: print('appel invalide : texte de référence et au moins un fichier de jugements attendus'); print('USAGE:', USAGE); return 2
    for f in a:
        if not os.path.isfile(f): print(f'appel invalide : fichier introuvable : {f}'); return 2
    if fjson and os.path.exists(fjson): print(f'appel invalide : {fjson} existe déjà (jamais écrasé)'); return 2
    T = lire_reference(a[0])
    if not T: print(f'appel invalide : aucun paragraphe lisible dans {a[0]} (format : paraId \\t T \\t section \\t texte)'); return 2
    jugements = []
    for f in a[1:]:
        try: J = json.load(open(f, encoding='utf-8'))
        except Exception as e: print(f'appel invalide : JSON illisible : {f} ({str(e)[:80]})'); return 2
        if not isinstance(J, list): print(f'appel invalide : {f} n\'est pas une liste de jugements'); return 2
        jugements.append((os.path.basename(f), J))
    b, lignes = verifier(T, jugements, racine)
    for l in lignes: print(l)
    print(f'Preuves vérifiées : {b["conformes"]} conformes, {b["echecs"]} en échec.')
    if b['hors_texte']: print('Preuves hors texte déclarées (à vérifier dans leur source) :', ', '.join(map(str, b['hors_texte'])))
    if b['sans_preuve']: print('Jugements sans preuve vérifiée :', ', '.join(map(str, b['sans_preuve'])))
    if b['verdicts_hors_liste']: print('Verdicts hors liste :', b['verdicts_hors_liste'])
    code = 1 if b['echecs'] or b['verdicts_hors_liste'] else (2 if b['sans_preuve'] else 0)
    if fjson:
        with open(fjson, 'x', encoding='utf-8') as o: json.dump(dict(b, echecs_detail=lignes, code=code), o, ensure_ascii=False, indent=1)
    evenement(OUTIL, VERSION, 'verification', dict(fichiers=len(jugements), conformes=b['conformes'], echecs=b['echecs'], code=code))
    return code


if __name__ == '__main__':
    sys.exit(main())
