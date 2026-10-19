"""
OUTIL: renumeroter_references
VERSION: 2
RESUME: Renumérote en suivi des modifications les références d'un rapport Word au format IEEE (citations « [n] », bibliographie « [n]<tab>… » sous le titre « Références ») dans l'ordre de leur première citation (vue « tout accepté », corps et annexes, sommaires exclus) : chaque citation « [ancien] » devient « [nouveau] » (seul le numéro change, moteur multi-auteurs) ; les entrées citées nulle part sont supprimées en suivi (la liste attendue doit être donnée et concorder) ; les entrées sont remises dans l'ordre par déplacements suivis (le moins possible : celles qui forment la plus longue suite déjà ordonnée restent en place ; les révisions et commentaires d'une entrée déplacée la suivent) ; l'étiquette de chaque entrée est renumérotée. Refuse une citation vers une entrée absente, une plage ou une liste « [a–b] », « [a, b] » et une liste à retirer qui ne concorde pas.
USAGE: python3 renumeroter_references_v2.py <entree.docx> <sortie.docx> --auteur "References - Claude" --retirer 2,4 [--json <bilan.json>]
ENTREES: docx (citations en texte simple, sans champ) ; numéros des entrées à retirer (contrôle : exactement les entrées citées nulle part)
SORTIES: <sortie.docx> (nouveau fichier, jamais écrasé : code 3 s'il existe) ; bilan (carte ancien → nouveau, citations modifiées, entrées retirées et déplacées) ; code 0, 2 usage, 4 refus (cas non pris en charge ou liste à retirer discordante)
CATEGORIE: revision_rapport
BANC: tests/test_renumeroter_references_v2.py
REMPLACE: renumeroter_references_v1 (remplaçait par la méthode replace de base du moteur, qui place le nouveau numéro À L'INTÉRIEUR de l'insertion d'un autre auteur quand la citation s'y trouve : le validateur du suivi (validate.py --original --author) ne reconnaissait plus leurs insertions et les comptait comme nouvelles ; passe par appliquer_texte (diff de jetons, replace_span multi-auteurs : notre insertion à côté, leur conteneur scindé) ; les étiquettes de la liste sont renumérotées après les déplacements, sur la copie déplacée, pour ne pas imbriquer nos propres révisions dans la source du déplacement ; identifiants de révision dédoublés après coup (un run scindé recopie la mise en forme suivie d'un autre auteur avec le même identifiant) ; jamais adoptée)
"""
import sys, os, re, json, bisect, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from moteur_revision_multi_v3 import DocR, q, W14, ln   # noqa: E402

VERSION = 2; OUTIL = 'renumeroter_references'
CIT = re.compile(r'\[(\d+)\]')
PLAGE = re.compile(r'\[\d+\s*[–\-,]\s*\d+')
ENTREE = re.compile(r'^\[(\d+)\]\t')


class Refus(Exception): pass


def style(p):
    s = p.find(q('pPr') + '/' + q('pStyle')); return s.get(q('val')) if s is not None else ''


def analyser(D):
    """(paragraphes, index du titre, entrées {n: pid} dans l'ordre, ordre de première citation, occurrences par pid)."""
    P = [(p.get('{%s}paraId' % W14), p) for p in D.plist]
    T = [D.ptext(p) for _, p in P]
    tit = [k for k, t in enumerate(T) if t.strip() == 'Références' and not style(P[k][1]).upper().startswith('TOC')]
    if len(tit) != 1: raise Refus(f'titre « Références » trouvé {len(tit)} fois')
    k0 = tit[0]; ent = {}; k = k0 + 1
    while k < len(T) and not ENTREE.match(T[k]): k += 1
    debut = k
    while k < len(T) and ENTREE.match(T[k]):
        n = int(ENTREE.match(T[k]).group(1))
        if n in ent: raise Refus(f'entrée [{n}] en double')
        ent[n] = P[k][0]; k += 1
    fin = k
    ordre, occ = [], collections.OrderedDict()
    for j, ((pid, p), t) in enumerate(zip(P, T)):
        if debut <= j < fin or style(p).upper().startswith('TOC'): continue
        if PLAGE.search(t): raise Refus(f'plage ou liste de citations non prise en charge dans {pid} : {PLAGE.search(t).group(0)}…')
        ns = [int(m.group(1)) for m in CIT.finditer(t)]
        for n in ns:
            if n not in ent: raise Refus(f'citation [{n}] sans entrée dans la bibliographie ({pid})')
            if n not in ordre: ordre.append(n)
        if ns: occ[pid] = ns
    return ent, ordre, occ


def plus_longue_suite(seq):
    """Indices d'une plus longue sous-suite croissante (entrées laissées en place)."""
    tails, tidx, prev = [], [], [-1] * len(seq)
    for i, v in enumerate(seq):
        j = bisect.bisect_left(tails, v)
        if j == len(tails): tails.append(v); tidx.append(i)
        else: tails[j] = v; tidx[j] = i
        prev[i] = tidx[j - 1] if j else -1
    out, k = set(), (tidx[-1] if tidx else -1)
    while k >= 0: out.add(k); k = prev[k]
    return out


def renumeroter(D, retirer):
    ent, ordre, occ = analyser(D)
    non_cites = sorted(set(ent) - set(ordre))
    if sorted(retirer) != non_cites: raise Refus(f'entrées à retirer {sorted(retirer)} ≠ entrées citées nulle part {non_cites}')
    carte = {old: new for new, old in enumerate(ordre, 1)}
    B = collections.Counter()
    # 1. citations : texte cible du paragraphe, appliqué par diff de jetons (replace_span, sûr en présence d'autres auteurs)
    for pid, ns in occ.items():
        t0 = D.text(pid); t1 = CIT.sub(lambda m: f'[{carte[int(m.group(1))]}]', t0)
        if t1 != t0:
            D.appliquer_texte(pid, t1); B['citations'] += sum(1 for n in ns if carte[n] != n)
    # 2. entrées : retrait, ordre (déplacements suivis), puis étiquettes sur la place finale
    for n in retirer: D.delete_paragraph(ent[n]); B['entrees_retirees'] += 1
    cur_ordre = [n for n in ent if n in carte]
    garde = {cur_ordre[i] for i in plus_longue_suite([carte[n] for n in cur_ordre])}
    place = {carte[n]: ent[n] for n in garde}                     # nouveau numéro -> paraId actuel
    deplaces = []
    for new in range(1, len(ordre) + 1):
        if new in place: continue
        old = ordre[new - 1]; pid = ent[old]
        avant = [k for k in place if k < new]; apres = [k for k in place if k > new]
        if avant: m = D.move_block(pid, pid, place[max(avant)], 'apres')
        else: m = D.move_block(pid, pid, place[min(apres)], 'avant')
        place[new] = m[pid]; deplaces.append(old); B['entrees_deplacees'] += 1
    for new, pid in place.items():
        old = ordre[new - 1]
        if old == new: continue
        t0 = D.text(pid)
        if not t0.startswith(f'[{old}]\t'): raise Refus(f'étiquette [{old}] introuvable au début de {pid}')
        D.appliquer_texte(pid, f'[{new}]' + t0[len(f'[{old}]'):]); B['etiquettes'] += 1
    # 3. identifiants de révision uniques (un run scindé recopie la mise en forme suivie d'un autre auteur)
    vus = set()
    for x in D.body.iter(*[q(t) for t in ('ins', 'del', 'moveFrom', 'moveTo', 'rPrChange', 'pPrChange')]):
        i = x.get(q('id'))
        if i is None: continue
        if i in vus: x.set(q('id'), D.rev_id()); B['identifiants_dedoubles'] += 1
        else: vus.add(i)
    return dict(carte={str(k): v for k, v in carte.items()}, retirees=sorted(retirer), deplacees=deplaces, laissees_en_place=len(garde),
                bilan=dict(B), ordre_final=[str(ordre[k - 1]) for k in sorted(place)])


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if len(a) < 4 or '--auteur' not in a: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    entree, sortie = a[0], a[1]
    if os.path.exists(sortie): print(f'existe déjà, jamais écrasé : {sortie}'); return 3
    auteur = a[a.index('--auteur') + 1]
    retirer = [int(x) for x in a[a.index('--retirer') + 1].split(',') if x.strip()] if '--retirer' in a else []
    D = DocR(entree, author=auteur, init='RF')
    try: R = renumeroter(D, retirer)
    except Refus as e: print(f'REFUS : {e}'); return 4
    D.save(sortie)
    print(f"renuméroté : {R['bilan']} ; en place {R['laissees_en_place']} ; déplacées {R['deplacees']}")
    if '--json' in a:
        with open(a[a.index('--json') + 1], 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)
    try:
        from cc_lib_v4 import evenement
        evenement(OUTIL, VERSION, 'renumerotation', R['bilan'])
    except Exception: pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
