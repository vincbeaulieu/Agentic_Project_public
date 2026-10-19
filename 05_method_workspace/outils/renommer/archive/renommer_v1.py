"""
OUTIL: renommer
VERSION: 1
RESUME: Renomme ou déplace des fichiers et dossiers d'après un plan JSON [[ancien, nouveau], …] (chemins relatifs à une racine), par os.rename seulement : jamais de copie, de suppression ni d'écrasement (refus si la cible existe) ; crée les dossiers parents ; essai à blanc possible ; même plan rejouable sur le cloud et sur le PC.
USAGE: python3 renommer_v1.py <racine> <plan.json> [--essai] [--ignorer-absents]
ENTREES: plan JSON : {"renommages": [["ancien", "nouveau"], …]}
SORTIES: liste des renommages ; code 0 ; événement dans journal/ (si l'espace de compétences est présent)
CATEGORIE: organisation
BANC: -
REMPLACE: 10_revision_01/scripts/renommer_dossiers_v2_appliquer.py (plan intégré au script)
"""
import sys, os, json
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
try:
    from cc_lib_v1 import evenement
except Exception:
    evenement = None


def main():
    racine, plan = sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8'))['renommages']
    essai = '--essai' in sys.argv; fait = deja = 0
    for a, b in plan:
        src, dst = os.path.join(racine, a), os.path.join(racine, b)
        if not os.path.exists(src):
            if os.path.exists(dst): print('déjà fait', a, '->', b); deja += 1; continue
            if '--ignorer-absents' in sys.argv: print('absent (ignoré)', a); continue
            raise SystemExit('ABSENT : ' + a)
        if os.path.exists(dst): raise SystemExit('CIBLE EXISTE : ' + b)
        if not essai:
            os.makedirs(os.path.dirname(dst), exist_ok=True); os.rename(src, dst)
        print('à renommer' if essai else 'renommé', a, '->', b); fait += 1
    print(f'{fait} renommage(s) {"prévu(s)" if essai else "fait(s)"} ; {deja} déjà fait(s)')
    if evenement and not essai: evenement('renommer', 1, 'renommage', dict(racine=os.path.basename(racine.rstrip('/')), n=fait))


if __name__ == '__main__':
    main()
