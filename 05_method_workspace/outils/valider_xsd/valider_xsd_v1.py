"""
OUTIL: valider_xsd
VERSION: 1
RESUME: Validation XSD absolue (sans comparaison à une source) de chaque partie XML d'un ou plusieurs docx, avec la partie, la ligne et le message de chaque erreur. validate.py --original, lui, masque une erreur déjà présente dans la source (cas du 16 oct. 2026 : marque de révision dans une équation, w:ins dans m:r, illisible dans Word). Les schémas que le validateur ne sait pas charger sont signalés à part (limite de l'outil, pas une erreur du document). Refuse bruyamment une liste vide, un fichier absent ou qui n'est pas un docx : appelé avec des arguments dans le désordre, l'ancien script de projet écrivait « {} » sans erreur.
CATALOGUE CONSULTÉ : « xsd schema validation docx » → aucun outil ; promotion du script de projet 16_version_finale/90_scripts/xsd_complet_v1.py (pilote des trois niveaux, outil de base).
USAGE: python3 outils/valider_xsd.py <f1.docx> [<f2.docx> …] --paquets <dossier> [--json <sortie.json>]
ENTREES: docx ; schémas et validateur du skill docx (/mnt/skills/public/docx/scripts/office) ; --paquets : dossier de travail où chaque docx est décompressé (un sous-dossier par fichier et par empreinte)
SORTIES: résumé à l'écran ; JSON facultatif {fichier: {erreurs: [{partie, ligne, message}], schemas_non_charges: [...]}} (jamais écrasé) ; événement dans le journal ; code 0 si aucune erreur, 1 sinon, 2 si l'appel est invalide
CATEGORIE: docx
BANC: tests/test_valider_xsd_v1.py
REMPLACE: - (script de projet xsd_complet_v1, non promu)
"""
import sys, os, json, zipfile, hashlib
from pathlib import Path
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from cc_lib_v5 import evenement                                         # noqa: E402

OUTIL, VERSION = 'valider_xsd', 1
OFFICE = os.environ.get('VALIDER_XSD_OFFICE', '/mnt/skills/public/docx/scripts/office')
USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def validateur():
    if not os.path.isdir(OFFICE): raise SystemExit(f'validateur du skill docx introuvable : {OFFICE}')
    if OFFICE not in sys.path: sys.path.insert(0, OFFICE)
    from validators import DOCXSchemaValidator
    from validators.base import _load_schema
    return DOCXSchemaValidator, _load_schema


def valider(f, paquets):
    """{erreurs: [...], schemas_non_charges: [...]} pour un docx."""
    import lxml.etree as LE
    V_, charger = validateur()
    d = Path(paquets).resolve() / (Path(f).stem + '_' + hashlib.sha256(open(f, 'rb').read()).hexdigest()[:12])
    if not d.exists():
        d.mkdir(parents=True)
        with zipfile.ZipFile(f) as z: z.extractall(d)
    V = V_(str(d), None); err, non = [], []
    for x in sorted(V.xml_files):
        sp = V._get_schema_path(x)
        if not sp: continue
        rel = str(x.relative_to(d))
        try: schema = charger(str(sp))
        except Exception as e: non.append(dict(partie=rel, message=str(e)[:160])); continue
        doc = LE.parse(str(x))
        doc, _ = V._remove_template_tags_from_text_nodes(doc); doc = V._preprocess_for_mc_ignorable(doc)
        if x.relative_to(d).parts and x.relative_to(d).parts[0] in V.MAIN_CONTENT_FOLDERS: doc = V._clean_ignorable_namespaces(doc)
        doc = V._preprocess_for_schema(doc, x.relative_to(d))
        if schema.validate(doc): continue
        for e in schema.error_log: err.append(dict(partie=rel, ligne=e.line, message=e.message[:300]))
    return dict(erreurs=err, schemas_non_charges=non)


def main(a=None):
    a = sys.argv[1:] if a is None else list(a)
    def opt(k):
        if k not in a: return None
        i = a.index(k)
        if i + 1 >= len(a): raise SystemExit(f'{k} sans valeur')
        v = a[i + 1]; del a[i:i + 2]; return v
    try: paquets, js = opt('--paquets'), opt('--json')
    except SystemExit as e: print(e, '\n' + USAGE); return 2
    fs = a
    if not fs or not paquets:
        print('appel invalide : au moins un docx et --paquets <dossier> sont exigés\n' + USAGE); return 2
    for f in fs:
        if not os.path.isfile(f): print(f'appel invalide : fichier introuvable : {f}'); return 2
        if not zipfile.is_zipfile(f) or 'word/document.xml' not in zipfile.ZipFile(f).namelist():
            print(f'appel invalide : pas un docx : {f}'); return 2
    if js and os.path.exists(js): print(f'appel invalide : {js} existe déjà (jamais d’écrasement)'); return 2
    R = {}
    for f in fs:
        r = valider(f, paquets); R[f] = r
        print(f"{os.path.basename(f)} : {len(r['erreurs'])} erreur(s) XSD" + (f" ; {len(r['schemas_non_charges'])} schéma(s) non chargeable(s) (limite de l'outil)" if r['schemas_non_charges'] else ''))
        for e in r['erreurs'][:12]: print(f"    {e['partie']} l. {e['ligne']} : {e['message'][:160]}")
    if js:
        with open(js, 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)
    n = sum(len(r['erreurs']) for r in R.values())
    evenement(OUTIL, VERSION, 'validation', dict(fichiers=len(fs), erreurs=n))
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
