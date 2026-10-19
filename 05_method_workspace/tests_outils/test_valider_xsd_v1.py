"""Tests de valider_xsd_v1 : docx sain sans erreur ; marque de révision dans une équation (w:ins dans m:r) détectée, le défaut
étant d'abord prouvé présent (LC-032) ; appels invalides refusés bruyamment (liste vide, --paquets absent, fichier absent, fichier qui
n'est pas un docx : cas du 16 oct. 2026 où l'ancien script écrivait « {} » sans erreur) ; JSON jamais écrasé ; ligne de commande.
Le validateur du skill docx est requis : sans lui (PC), la suite est ignorée, et le dit."""
import os, sys, json, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version

OUTIL = chemin_version('valider_xsd', 1)
V = importer_version('valider_xsd', 1)
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
SAIN = '<w:p><w:r><w:t>Texte sain.</w:t></w:r></w:p>'
EQUATION = ('<w:p><m:oMath><m:r><w:ins w:id="1" w:author="Essai" w:date="2026-01-01T00:00:00Z"><m:t>x</m:t></w:ins></m:r></m:oMath></w:p>')


def docx(d, nom, corps):
    f = os.path.join(d, nom)
    with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', TYPES); z.writestr('_rels/.rels', RELS)
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{corps}<w:sectPr/></w:body></w:document>')
    return f


@unittest.skipUnless(os.path.isdir(V.OFFICE), 'validateur du skill docx absent de cet espace')
class Validation(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('valider_xsd_v1'); self.paq = os.path.join(self.d, 'paquets')

    def test_docx_sain(self):
        r = V.valider(docx(self.d, 'sain_v1.docx', SAIN), self.paq)
        self.assertEqual(r['erreurs'], [], r)

    def test_revision_dans_une_equation(self):
        f = docx(self.d, 'equation_v1.docx', EQUATION)
        with zipfile.ZipFile(f) as z: self.assertIn('<m:r><w:ins', z.read('word/document.xml').decode())   # le défaut est bien injecté
        r = V.valider(f, self.paq)
        self.assertTrue(any(e['partie'] == 'word/document.xml' for e in r['erreurs']), r)

    def test_appels_invalides(self):
        f = docx(self.d, 'sain_v1.docx', SAIN); txt = os.path.join(self.d, 'note_v1.txt'); open(txt, 'x').write('pas un docx')
        for args in ([], [f], ['--paquets', self.paq], [os.path.join(self.d, 'absent_v1.docx'), '--paquets', self.paq], [txt, '--paquets', self.paq], [f, '--paquets']):
            self.assertEqual(V.main(args), 2, args)

    def test_ligne_de_commande_et_json(self):
        f = docx(self.d, 'equation_v1.docx', EQUATION); j = os.path.join(self.d, 'xsd_v1.json')
        r = subprocess.run([sys.executable, OUTIL, f, '--paquets', self.paq, '--json', j], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr); self.assertIn('erreur(s) XSD', r.stdout)
        with open(j, encoding='utf-8') as g: self.assertTrue(json.load(g)[f]['erreurs'])
        r2 = subprocess.run([sys.executable, OUTIL, f, '--paquets', self.paq, '--json', j], capture_output=True, text=True)
        self.assertEqual(r2.returncode, 2); self.assertIn('existe déjà', r2.stdout)
        r3 = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True)
        self.assertEqual(r3.returncode, 2); self.assertIn('appel invalide', r3.stdout)


if __name__ == '__main__':
    unittest.main()
