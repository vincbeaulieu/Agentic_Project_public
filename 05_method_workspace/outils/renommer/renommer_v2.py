"""
OUTIL: renommer
VERSION: 2
RESUME: Renomme ou déplace des fichiers et dossiers d'après un plan JSON [[ancien, nouveau], …] (chemins relatifs à une racine), par os.rename seulement : jamais de copie, de suppression ni d'écrasement (refus si la cible existe) ; crée les dossiers parents ; essai à blanc possible ; même plan rejouable sur le cloud et sur le PC.
USAGE: python3 renommer_v2.py <racine> <plan.json> [--essai] [--ignorer-absents]
ENTREES: plan JSON : {"renommages": [["ancien", "nouveau"], …]}
SORTIES: liste des renommages ; code 0 ; événement dans journal/ (si l'espace de compétences est présent)
CATEGORIE: organisation
BANC: tests/test_renommer_v2.py
REMPLACE: renommer_v1 (le plan entier est validé avant le premier renommage, essai à blanc compris : sources présentes, cibles libres et distinctes, sinon tous les écarts sont listés et rien n'est renommé, au lieu d'un plan appliqué à moitié ; sans argument, affiche USAGE et sort avec le code 2) ; v1 : 10_revision_01/scripts/renommer_dossiers_v2_appliquer.py (plan intégré au script)
"""
import sys, os, json
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
try:
    from cc_lib_v1 import evenement
except Exception:
    evenement = None


def valider(racine, plan, ignorer):
    """Simule le plan, ligne après ligne, sur l'état du disque (un renommage prévu libère sa source et occupe sa cible). Ne modifie rien.
    Renvoie (lignes, ecarts) : lignes = [(statut, ancien, nouveau)] avec statut « faire », « deja » ou « ignore » ; ecarts = messages."""
    lignes, ecarts, prevus = [], [], []
    def origine(p):                                     # emplacement du disque d'où vient ce chemin après les renommages prévus
        for s, d in reversed(prevus):
            if p == d or p.startswith(d + os.sep): p = s + p[len(d):]
            elif p == s or p.startswith(s + os.sep): return None
        return p
    def existe(p):
        o = origine(p)
        return any(d.startswith(p + os.sep) for _, d in prevus) or (o is not None and os.path.exists(o))
    for a, b in plan:
        src, dst = os.path.normpath(os.path.join(racine, a)), os.path.normpath(os.path.join(racine, b))
        if not existe(src):
            if existe(dst): lignes.append(('deja', a, b))
            elif ignorer: lignes.append(('ignore', a, b))
            else: ecarts.append(('SOURCE EN DOUBLE : ' if any(s == src for s, _ in prevus) else 'ABSENT : ') + a)
        elif existe(dst): ecarts.append(('CIBLE EN DOUBLE : ' if any(d == dst for _, d in prevus) else 'CIBLE EXISTE : ') + b)
        else: prevus.append((src, dst)); lignes.append(('faire', a, b))
    return lignes, ecarts


def main():
    args = [x for x in sys.argv[1:] if not x.startswith('--')]
    if len(args) < 2: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    racine, plan = args[0], json.load(open(args[1], encoding='utf-8'))['renommages']
    essai = '--essai' in sys.argv; fait = deja = 0
    lignes, ecarts = valider(racine, plan, '--ignorer-absents' in sys.argv)
    if ecarts: raise SystemExit('\n'.join(ecarts) + f'\nPLAN REFUSE : {len(ecarts)} écart(s), aucun renommage effectué')
    for statut, a, b in lignes:
        if statut == 'deja': print('déjà fait', a, '->', b); deja += 1; continue
        if statut == 'ignore': print('absent (ignoré)', a); continue
        src, dst = os.path.join(racine, a), os.path.join(racine, b)
        if not essai:
            os.makedirs(os.path.dirname(dst), exist_ok=True); os.rename(src, dst)
        print('à renommer' if essai else 'renommé', a, '->', b); fait += 1
    print(f'{fait} renommage(s) {"prévu(s)" if essai else "fait(s)"} ; {deja} déjà fait(s)')
    if evenement and not essai: evenement('renommer', 2, 'renommage', dict(racine=os.path.basename(racine.rstrip('/')), n=fait))


if __name__ == '__main__':
    sys.exit(main())
