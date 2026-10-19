"""
OUTIL: livrer
VERSION: 3
RESUME: Remise d'un livrable par construction conforme : copie chaque fichier dans 98_livrables sous le nom <Nom>_v<version>[_variante].<ext> (version = version_cible de TRAVAIL, égale à la version attendue : décision de l'utilisateur pour ce document, sinon v(X+1).0.0), en lecture seule, ajoute son empreinte à empreintes_livrables_v<version>.txt et sa copie modifiable dans 99_livrables_modifiables ; refuse tout nom existant ; lance ensuite evaluer_travail.
USAGE: python3 livrer_v3.py <dossier_de_travail> <fichier>:<Nom>[:<variante>] [...] [--sans-evaluation]
ENTREES: fichiers produits dans les étapes du dossier ; TRAVAIL_vN.json (version_cible)
SORTIES: 98_livrables/…, 99_livrables_modifiables/…, empreintes ; verdict de evaluer_travail ; événement dans journal/
CATEGORIE: organisation
BANC: -
REMPLACE: livrer_v2 (version vérifiée avant la remise : version_cible de TRAVAIL = version attendue — règle ou décision de l'utilisateur propre au document, consignée dans TRAVAIL « decision_version », sinon v(X+1).0.0 — par cc_lib_v3.version_attendue ; v2 exigeait M.0.0 et acceptait toute valeur de version_cible) ; v2 : livrer_v1 (lance la version courante de evaluer_travail d'après le registre, au lieu de evaluer_travail_v1 figé)
"""
import sys, os, re, json, shutil, stat, subprocess, glob
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v2 import chemin_outil
from cc_lib_v3 import version_attendue
from cc_lib_v1 import h16, evenement, version_tuple


def main():
    a = sys.argv[1:]; d = os.path.abspath(a[0])
    ft = sorted(glob.glob(os.path.join(d, 'TRAVAIL_v*.json')), key=lambda f: version_tuple(re.search(r'_v(\d+)', f).group(1)))
    if not ft: raise SystemExit('TRAVAIL_vN.json absent : créer le dossier avec creer_travail_v1.py')
    T = json.load(open(ft[-1], encoding='utf-8')); M = str(T['version_cible']); att, origine = version_attendue(T)
    if att is None and not re.match(r'^\d+\.0\.0$', M): raise SystemExit(f'version_cible {M} : source illisible, attendu M.0.0')
    if att is not None and M != att: raise SystemExit(f'version_cible {M} ≠ {att} attendue ({origine}) : corriger TRAVAIL (nouvelle version) avant la remise')
    liv, mod = os.path.join(d, '98_livrables'), os.path.join(d, '99_livrables_modifiables')
    os.makedirs(liv, exist_ok=True); os.makedirs(mod, exist_ok=True)
    femp = os.path.join(liv, f'empreintes_livrables_v{M}.txt')
    lignes = open(femp, encoding='utf-8').read().splitlines() if os.path.exists(femp) else []
    remis = []
    for spec in [x for x in a[1:] if not x.startswith('--')]:
        parts = spec.split(':')
        f, nom = parts[0], parts[1]; var = parts[2] if len(parts) > 2 else None
        ext = os.path.splitext(f)[1].lstrip('.')
        if not re.match(r'^[A-Za-z0-9][A-Za-z0-9_\-]*$', nom): raise SystemExit(f'nom {nom!r} : lettres, chiffres, _ et - seulement')
        cible = f"{nom}_v{M}{'_' + var if var else ''}.{ext}"
        for dd in (liv, mod):
            if os.path.exists(os.path.join(dd, cible)): raise SystemExit(f'existe déjà : {os.path.join(dd, cible)} (jamais d’écrasement : monter la version cible)')
        shutil.copy2(f, os.path.join(liv, cible)); shutil.copy2(f, os.path.join(mod, cible))
        os.chmod(os.path.join(liv, cible), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        lignes.append(f'{h16(os.path.join(liv, cible))} {cible}'); remis.append(cible)
    if os.path.exists(femp):
        os.chmod(femp, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        ancien = open(femp, encoding='utf-8').read()
        nouveau = '\n'.join(lignes) + '\n'
        assert nouveau.startswith(ancien), 'empreintes : ajout seul'
        open(femp, 'w', encoding='utf-8').write(nouveau)
    else:
        open(femp, 'x', encoding='utf-8').write('\n'.join(lignes) + '\n')
    evenement('livrer', 3, 'remise', dict(dossier=os.path.basename(d), version=M, fichiers=remis))
    print('remis :', ', '.join(remis))
    if '--sans-evaluation' not in a:
        sys.exit(subprocess.run([sys.executable, chemin_outil('evaluer_travail'), d]).returncode)


if __name__ == '__main__':
    main()
