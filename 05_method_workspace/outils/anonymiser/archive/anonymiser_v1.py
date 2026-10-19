"""
OUTIL: anonymiser
VERSION: 1
RESUME: Anonymisation déterministe de mes propres documents (règle E13 du mémoire) : chaque suite de mots dont l'empreinte figure dans regles/roles_vN.json est remplacée par un rôle (Utilisateur, Collègue A, B, C…), sans stocker de noms en clair ; écrit une NOUVELLE version de chaque fichier (jamais d'écrasement) et vérifie qu'il ne reste aucun nom protégé.
USAGE: python3 anonymiser_v1.py <fichier> [<fichier> …]   (fichiers texte versionnés : md, txt, json, jsonl, py, csv)
ENTREES: fichiers nom_vN.ext ; regles/roles_vN.json ; regles/noms_proteges_vN.json
SORTIES: nom_v(N+1).ext à côté de chaque fichier ; « reste : 0 » ; événement dans journal/
CATEGORIE: confidentialite
BANC: -
REMPLACE: -
"""
import sys, os, re, json, hashlib, unicodedata
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from cc_lib_v1 import RACINE_CC, evenement, derniere_version
MOT = re.compile(r"(?:[dD]['’])?[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[  ][A-Za-zÀ-ÖØ-öø-ÿ]+)*")


def norm(t): return ''.join(c for c in unicodedata.normalize('NFKD', t.lower()) if not unicodedata.combining(c))
def emp(t): return hashlib.sha256(('cc-noms|' + norm(t)).encode()).hexdigest()[:16]


def anonymiser(texte, roles):
    def rempl(m):
        bloc = m.group(0); pre = ''
        if re.match(r"[dD]['’]", bloc): pre, bloc = bloc[:2], bloc[2:]
        mots = re.split(r'([  ])', bloc); out = []; i = 0
        while i < len(mots):
            w = mots[i]
            if w and w not in (' ', ' ') and emp(w) in roles:
                role = roles[emp(w)]; j = i
                while j + 2 < len(mots) and emp(mots[j + 2]) in roles and roles[emp(mots[j + 2])] == role: j += 2
                if not out and pre and role[0] not in 'AEIOUÉaeiouéUu': out.append('de '); pre = ''
                out.append(role); i = j + 1
            else:
                out.append(w); i += 1
        return pre + ''.join(out)
    return MOT.sub(rempl, texte)


def main():
    roles = json.load(open(derniere_version(os.path.join(RACINE_CC, 'regles'), 'roles', 'json'), encoding='utf-8'))['roles']
    proteges = set(json.load(open(derniere_version(os.path.join(RACINE_CC, 'regles'), 'noms_proteges', 'json'), encoding='utf-8'))['empreintes'])
    faits = 0
    for f in sys.argv[1:]:
        m = re.match(r'^(.*)_v(\d+)(\.[A-Za-z0-9]+)$', f)
        if not m: print('ignoré (sans version simple _vN) :', f); continue
        cible = f'{m.group(1)}_v{int(m.group(2)) + 1}{m.group(3)}'
        if os.path.exists(cible): print('existe déjà, ignoré :', cible); continue
        t = open(f, encoding='utf-8').read(); a = anonymiser(t, roles)
        reste = sum(1 for w in re.findall(r'[A-Za-zÀ-ÖØ-öø-ÿ]+', a) if emp(w) in proteges)
        if f.endswith('.json'):
            json.loads(a)
        with open(cible, 'x', encoding='utf-8') as fo: fo.write(a)
        faits += 1; print(f'{os.path.basename(cible)} (reste : {reste})')
    evenement('anonymiser', 1, 'anonymisation', dict(fichiers=faits))


if __name__ == '__main__':
    main()
