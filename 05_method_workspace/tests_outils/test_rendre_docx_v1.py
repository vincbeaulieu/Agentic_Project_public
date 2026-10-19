"""Tests de rendre_docx_v1 : docx sain rendu (pages, PNG, images extraites) ; docx que LibreOffice refuse signalé (code 1), le
défaut étant d'abord prouvé présent (fichier tronqué) ; dossier de sortie existant refusé (jamais d'écrasement) ; appels invalides.
LibreOffice et poppler sont requis : sans eux, la suite est ignorée, et le dit."""
import os, sys, json, shutil, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version

OUTIL = chemin_version('rendre_docx', 1)
R = importer_version('rendre_docx', 1)
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
         '<Default Extension="png" ContentType="image/png"/>'
         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')


def docx(d, nom, media=False):
    f = os.path.join(d, nom)
    with zipfile.ZipFile(f, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', TYPES); z.writestr('_rels/.rels', RELS)
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body><w:p><w:r><w:t>Page de rendu.</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
        if media: z.writestr('word/media/image1.png', PNG)
    return f


@unittest.skipUnless(shutil.which('soffice') and shutil.which('pdfinfo') and shutil.which('pdftoppm'), 'LibreOffice ou poppler absent de cet espace')
class Rendu(unittest.TestCase):
    def setUp(self): self.d = dossier_essai('rendre_docx_v1')

    def test_docx_sain(self):
        s = os.path.join(self.d, 'rendu_sain')
        r = R.rendre(docx(self.d, 'sain_v1.docx', media=True), s)
        self.assertIsNone(r['refus']); self.assertGreaterEqual(r['pages'], 1); self.assertEqual(len(r['png']), r['pages'])
        self.assertEqual([os.path.basename(x) for x in r['images']], ['image1.png'])
        self.assertFalse(os.path.exists(os.path.join(s, 'lo_profile')))

    def test_docx_refuse(self):
        data = open(docx(self.d, 'sain_v1.docx'), 'rb').read(); f = os.path.join(self.d, 'casse_v1.docx')
        with open(f, 'xb') as g: g.write(data[: len(data) // 3])                       # docx tronqué (nouveau fichier)
        self.assertFalse(zipfile.is_zipfile(f))                                         # le défaut est bien injecté
        r = R.rendre(f, os.path.join(self.d, 'rendu_casse'))
        self.assertEqual(r['pages'], 0); self.assertTrue(r['refus'])

    def test_ligne_de_commande(self):
        f = docx(self.d, 'sain_v1.docx'); s = os.path.join(self.d, 'rendu_cli')
        p = subprocess.run([sys.executable, OUTIL, f, '--sortie', s], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr); self.assertIn('page(s)', p.stdout)
        with open(os.path.join(s, 'rendu_v1.json'), encoding='utf-8') as g: self.assertGreaterEqual(json.load(g)['pages'], 1)
        p2 = subprocess.run([sys.executable, OUTIL, f, '--sortie', s], capture_output=True, text=True)
        self.assertEqual(p2.returncode, 2); self.assertIn('existe déjà', p2.stdout)
        self.assertEqual(R.main([f]), 2); self.assertEqual(R.main(['--sortie', os.path.join(self.d, 'x')]), 2)


if __name__ == '__main__':
    unittest.main()
