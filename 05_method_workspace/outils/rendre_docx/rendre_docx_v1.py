"""
OUTIL: rendre_docx
VERSION: 1
RESUME: Ouverture réelle d'un docx par LibreOffice (conversion en PDF), nombre de pages, puis rendu de chaque page en PNG pour qu'on la regarde, et extraction des images du document (word/media) pour qu'on les regarde aussi. Un docx que LibreOffice refuse est signalé bruyamment (code 1), jamais pris pour un succès : un document accepté par les validateurs peut être refusé à l'ouverture (cas du 16 oct. 2026, espaces de noms ns0).
CATALOGUE CONSULTÉ : « rendu pdf png libreoffice pages » → aucun outil ; rendu refait à la main à chaque livraison (porte_livraison_v1, script de projet du dossier 17) : outil de base nouveau (pilote des trois niveaux).
USAGE: python3 outils/rendre_docx.py <docx> --sortie <dossier neuf> [--resolution 60]
ENTREES: docx ; soffice (LibreOffice), pdfinfo et pdftoppm (poppler)
SORTIES: <sortie>/<nom>.pdf, <sortie>/page-N.png, <sortie>/images/<fichier> ; résumé {pages, png, images} à l'écran et dans <sortie>/rendu_v1.json ; événement dans le journal ; code 0 si au moins une page, 1 si LibreOffice refuse le document, 2 si l'appel est invalide (dossier de sortie déjà existant : jamais d'écrasement)
CATEGORIE: docx
BANC: tests/test_rendre_docx_v1.py
REMPLACE: -
"""
import sys, os, re, json, glob, shutil, zipfile, subprocess
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from cc_lib_v5 import evenement                                         # noqa: E402

OUTIL, VERSION = 'rendre_docx', 1
USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def rendre(docx, sortie, resolution=60):
    """Rend {pages, pdf, png: [...], images: [...], refus: message ou None}. Le dossier de sortie doit être neuf."""
    os.makedirs(sortie)
    nom = os.path.splitext(os.path.basename(docx))[0]; S = os.path.abspath(sortie)
    r = subprocess.run(['soffice', f'-env:UserInstallation=file://{S}/lo_profile', '--headless', '--convert-to', 'pdf', '--outdir', S, os.path.abspath(docx)],
                       capture_output=True, text=True, timeout=170)
    pdf = os.path.join(S, nom + '.pdf'); pages = 0; refus = None
    if os.path.exists(pdf):
        m = re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout)
        pages = int(m.group(1)) if m else 0
    if not pages: refus = (r.stdout + r.stderr).strip()[-300:] or 'aucun PDF produit'
    else: subprocess.run(['pdftoppm', '-r', str(resolution), '-png', pdf, os.path.join(S, 'page')], capture_output=True, timeout=170)
    png = sorted(glob.glob(os.path.join(S, 'page-*.png')), key=lambda f: int(re.search(r'-(\d+)\.png$', f).group(1)))
    images = []
    if zipfile.is_zipfile(docx):
        z = zipfile.ZipFile(docx); md = [x for x in z.namelist() if x.startswith('word/media/')]
        if md: os.makedirs(os.path.join(S, 'images'))
        for x in md:
            c = os.path.join(S, 'images', os.path.basename(x))
            with open(c, 'xb') as g: g.write(z.read(x))
            images.append(c)
    shutil.rmtree(os.path.join(S, 'lo_profile'), ignore_errors=True)   # profil LibreOffice : jamais sauvegardé (règle sync-cloud-pc)
    return dict(docx=docx, pdf=pdf if pages else None, pages=pages, png=png, images=images, refus=refus)


def main(a=None):
    a = sys.argv[1:] if a is None else list(a)
    if '--sortie' not in a or a.index('--sortie') + 1 >= len(a): print('appel invalide : --sortie <dossier neuf> est exigé\n' + USAGE); return 2
    i = a.index('--sortie'); sortie = a[i + 1]; del a[i:i + 2]
    res = 60
    if '--resolution' in a:
        j = a.index('--resolution'); res = int(a[j + 1]); del a[j:j + 2]
    if len(a) != 1 or not os.path.isfile(a[0]): print('appel invalide : un docx existant est exigé\n' + USAGE); return 2
    if os.path.exists(sortie): print(f'appel invalide : {sortie} existe déjà (jamais d’écrasement : choisir un dossier neuf)'); return 2
    R = rendre(a[0], sortie, res)
    with open(os.path.join(sortie, 'rendu_v1.json'), 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)
    if R['refus']: print(f"REFUSÉ par LibreOffice : {os.path.basename(a[0])} : {R['refus']}")
    else: print(f"{os.path.basename(a[0])} : {R['pages']} page(s), {len(R['png'])} PNG, {len(R['images'])} image(s) extraite(s) dans {sortie}")
    evenement(OUTIL, VERSION, 'rendu', dict(pages=R['pages'], images=len(R['images']), refuse=bool(R['refus'])))
    return 1 if R['refus'] else 0


if __name__ == '__main__':
    sys.exit(main())
