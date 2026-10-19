"""Tests de livrer_v5 (mêmes cas que livrer_v4, plus la fiche TRAVAIL lue sur son nom) : un fichier texte est remis comme en v3 ; un docx passe la porte de livraison et n'est remis que si chaque porte
est conforme. Tests négatifs, un par porte, le défaut étant d'abord prouvé présent (LC-032) : docx sans référence de mise en forme
(appel refusé) ; pages non déclarées regardées ; page déclarée hors du document ; images non regardées ; mise en forme différente de la
référence (Calibri 9,5 pt et titres bleus au lieu de Times New Roman 11 pt : erreur 6 du 16 oct. 2026) ; marque de révision dans une
équation (XSD absolu). La porte « noms protégés » n'a pas encore de test négatif : detecter_noms ne prend pas de registre fictif, et
aucun vrai nom ne peut figurer dans un test (à faire : detecter_noms v3 --registre). Rien n'est jamais remis après un échec.
LibreOffice, poppler et le validateur du skill docx sont requis pour les docx : sans eux, ces tests sont ignorés, et le disent."""
import os, re, sys, json, shutil, zipfile, subprocess, unittest, importlib.util
from aide_tests_v2 import dossier_essai, chemin_version, chemin

spec = importlib.util.spec_from_file_location('cas_evaluer', chemin('bancs', 'evaluer_travail', 'cas_v1.py'))
CAS = importlib.util.module_from_spec(spec); spec.loader.exec_module(CAS)
LIVRER = chemin_version('livrer', 5)
OFFICE = '/mnt/skills/public/docx/scripts/office'
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
         '<Default Extension="png" ContentType="image/png"/>'
         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
         '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
DOCRELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
           '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')
CORPS = ('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Bilan</w:t></w:r></w:p>'
         '<w:p><w:r><w:t>Un paragraphe de corps au format du document de référence.</w:t></w:r></w:p>')
EQUATION = '<w:p><m:oMath><m:r><w:ins w:id="1" w:author="Essai" w:date="2026-01-01T00:00:00Z"><m:t>x</m:t></w:ins></m:r></m:oMath></w:p>'


def styles(police='Times New Roman', sz='22', couleur=None):
    c = f'<w:color w:val="{couleur}"/>' if couleur else ''
    return (f'<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{police}" w:hAnsi="{police}"/><w:sz w:val="{sz}"/></w:rPr></w:rPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            f'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:rPr><w:b/>{c}<w:sz w:val="30"/></w:rPr></w:style></w:styles>')


def docx(d, nom, corps=CORPS, st=None, media=False):
    os.makedirs(d, exist_ok=True); f = os.path.join(d, nom)
    with zipfile.ZipFile(f, 'x', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', TYPES); z.writestr('_rels/.rels', RELS); z.writestr('word/_rels/document.xml.rels', DOCRELS)
        z.writestr('word/document.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{corps}<w:sectPr/></w:body></w:document>')
        z.writestr('word/styles.xml', st or styles())
        if media: z.writestr('word/media/image1.png', PNG)
    return f


def dossier(nom):
    """Dossier de travail conforme, livrables vidés, source « Rapport_v1.0.0.docx » (le journal en est un document annexe)."""
    d = os.path.join(dossier_essai(nom), '11_essai_livrer')
    CAS._ecrire(d, 'LISEZMOI_v1.md', '# Essai\n'); CAS._ecrire(d, '00_sources/Rapport_v1.0.0.docx', 'source\n', ro=True)
    CAS._ecrire(d, '00_sources/sha256_sources_v1.txt', f'{CAS._sha("source" + chr(10))}  00_sources/Rapport_v1.0.0.docx\n', ro=True)
    CAS._ecrire(d, '95_journal/audit_v1.md', 'a\n')
    T = dict(sujet='essai', source='00_sources/Rapport_v1.0.0.docx', auteur_revisions='Essai - Claude', version_cible='2.0.0', couverture=None, auteurs_relecteurs=[])
    CAS._ecrire(d, 'TRAVAIL_v1.json', json.dumps(T))
    CAS._ecrire(d, '01_etape/resultat_v1.md', 'résultat\n')
    os.makedirs(os.path.join(d, '98_livrables')); os.makedirs(os.path.join(d, '99_livrables_modifiables'))
    return d


def lancer(*a):
    r = subprocess.run([sys.executable, LIVRER] + list(a), capture_output=True, text=True, timeout=600); return r.returncode, r.stdout + r.stderr


def remis(d): return sorted(os.listdir(os.path.join(d, '98_livrables')))


class Texte(unittest.TestCase):
    def test_fichier_texte_remis_sans_porte(self):
        d = dossier('livrer4_texte')
        c, s = lancer(d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Note', '--sans-evaluation')
        self.assertEqual(c, 0, s); self.assertEqual(remis(d), ['Note_v2.0.0.md', 'empreintes_livrables_v2.0.0.txt'])

    def test_docx_sans_reference_refuse(self):
        d = dossier('livrer4_sans_ref'); j = docx(os.path.join(d, '01_etape'), 'Journal_v1.docx')
        c, s = lancer(d, j + ':Journal', '--sans-evaluation', '--pages-vues', '1')
        self.assertEqual(c, 2, s); self.assertIn('sans document de référence', s); self.assertEqual(remis(d), [])


@unittest.skipUnless(shutil.which('soffice') and shutil.which('pdftoppm') and os.path.isdir(OFFICE), 'LibreOffice, poppler ou validateur docx absent')
class PorteDocx(unittest.TestCase):
    def setUp(self):
        self.d = dossier('livrer4_porte_' + self._testMethodName[5:25])
        self.ref = docx(os.path.join(self.d, '01_etape'), 'Rapport_reference_v1.docx')

    def fiche(self):
        P = os.path.join(self.d, '95_journal', 'portes'); fs = sorted(f for f in os.listdir(P) if f.endswith('.md'))
        self.assertEqual(len(fs), 1, fs)
        with open(os.path.join(P, fs[0]), encoding='utf-8') as g: return g.read()

    def test_conforme_remis(self):
        j = docx(os.path.join(self.d, '01_etape'), 'Journal_v1.docx')
        c, s = lancer(self.d, j + ':Journal', '--sans-evaluation', '--reference', self.ref, '--pages-vues', '1')
        self.assertEqual(c, 0, s); self.assertEqual(remis(self.d), ['Journal_v2.0.0.docx', 'empreintes_livrables_v2.0.0.txt'])
        self.assertIn('verdict : **CONFORME**', self.fiche())

    def test_porte_seule_rien_remis(self):
        j = docx(os.path.join(self.d, '01_etape'), 'Journal_v1.docx')
        c, s = lancer(self.d, j + ':Journal', '--porte-seule', '--reference', self.ref)
        self.assertEqual(c, 0, s); self.assertEqual(remis(self.d), [])                    # porte seule : contrôles automatiques passés, rien remis
        self.assertIn('Pages regardées (--pages-vues) | à faire (regarder les rendus)', self.fiche())
        rendus = [x for x in os.listdir(os.path.join(self.d, '95_journal', 'portes')) if not x.endswith('.md')]
        self.assertTrue(os.listdir(os.path.join(self.d, '95_journal', 'portes', rendus[0], 'rendu')))

    def test_page_hors_document(self):
        j = docx(os.path.join(self.d, '01_etape'), 'Journal_v1.docx')
        c, s = lancer(self.d, j + ':Journal', '--sans-evaluation', '--reference', self.ref, '--pages-vues', '9')
        self.assertEqual(c, 1, s); self.assertEqual(remis(self.d), [])

    def test_images_non_regardees(self):
        j = docx(os.path.join(self.d, '01_etape'), 'Journal_v1.docx', media=True)
        with zipfile.ZipFile(j) as z: self.assertIn('word/media/image1.png', z.namelist())      # le défaut est bien injecté
        c, s = lancer(self.d, j + ':Journal', '--sans-evaluation', '--reference', self.ref, '--pages-vues', '1')
        self.assertEqual(c, 1, s); self.assertEqual(remis(self.d), []); self.assertIn('1 image(s) ; 0 déclarée(s) regardée(s)', self.fiche())

    def test_format_different_refuse(self):
        j = docx(os.path.join(self.d, '01_etape'), 'Journal_v1.docx', st=styles('Calibri', '19', '1F3864'))
        with zipfile.ZipFile(j) as z: self.assertIn('w:ascii="Calibri"', z.read('word/styles.xml').decode())   # le défaut est bien injecté
        c, s = lancer(self.d, j + ':Journal', '--sans-evaluation', '--reference', self.ref, '--pages-vues', '1')
        self.assertEqual(c, 1, s); self.assertEqual(remis(self.d), [])
        self.assertRegex(self.fiche(), r'Mise en forme identique à la référence .* \| \*\*non conforme\*\*')

    def test_xsd_absolu_refuse(self):
        j = docx(os.path.join(self.d, '01_etape'), 'Journal_v1.docx', corps=CORPS + EQUATION)
        with zipfile.ZipFile(j) as z: self.assertIn('<m:r><w:ins', z.read('word/document.xml').decode())     # le défaut est bien injecté
        c, s = lancer(self.d, j + ':Journal', '--sans-evaluation', '--reference', self.ref, '--pages-vues', '1')
        self.assertEqual(c, 1, s); self.assertEqual(remis(self.d), [])
        self.assertIn('Validation XSD absolue (valider_xsd) | **non conforme**', self.fiche())


if __name__ == '__main__':
    unittest.main()


class FicheTravail(unittest.TestCase):
    """Défaut du 18 oct. 2026 : livrer_v4 lisait la version de TRAVAIL_vN.json sur le chemin complet ; dans un dossier dont le nom
    contient « _vN » (17_comparaison_v6.0.4), toutes les fiches avaient la même clé, et la v1 a été prise pour la dernière."""

    def fiches(self, nom):
        d = dossier(nom)
        T = json.load(open(os.path.join(d, 'TRAVAIL_v1.json'), encoding='utf-8'))
        T2 = dict(T, version_cible='3.0.0', decision_version=dict(valeur='3.0.0', approuvee_par='utilisateur', portee='essai', citations=['« 3.0.0 »']))
        CAS._ecrire(d, 'TRAVAIL_v2.json', json.dumps(T2))
        T10 = dict(T2, version_cible='4.0.0', decision_version=dict(T2['decision_version'], valeur='4.0.0'))
        CAS._ecrire(d, 'TRAVAIL_v10.json', json.dumps(T10))
        return d

    def test_defaut_present_avec_la_cle_v4(self):
        d = self.fiches('livrer5_v6.0.4_cle')
        f = [os.path.join(d, n) for n in ('TRAVAIL_v1.json', 'TRAVAIL_v2.json', 'TRAVAIL_v10.json')]
        cles_v4 = {re.search(r'_v(\d+)', x).group(1) for x in f}
        self.assertEqual(cles_v4, {'6'}, 'le défaut doit être présent : la clé de la v4 ne distingue pas les fiches')
        cles_v5 = [int(re.search(r'^TRAVAIL_v(\d+)\.json$', os.path.basename(x)).group(1)) for x in f]
        self.assertEqual(cles_v5, [1, 2, 10])

    def test_derniere_fiche_numerique_retenue(self):
        d = self.fiches('livrer5_v6.0.4_remise')
        c, s = lancer(d, os.path.join(d, '01_etape', 'resultat_v1.md') + ':Note', '--sans-evaluation')
        self.assertEqual(c, 0, s); self.assertEqual(remis(d), ['Note_v4.0.0.md', 'empreintes_livrables_v4.0.0.txt'])
