"""v2 de la suite (détecteurs dans leur version courante). Tests de reparer_fragments_v2 (exemples synthétiques reproduisant le défaut : insertion placée en fin de paragraphe au lieu
de sa place) : sigle répété collé, fragment collé après un point (majuscule, mot d'une lettre), dernière phrase sans ponctuation
finale, trou en début de paragraphe ; refus si les nombres diffèrent ; trou déjà présent dans la vue d'origine ignoré ; noms de
fichiers non pris pour des fragments ; module d'opérations et aperçu produits sur un docx d'essai."""
import os, sys, zipfile, subprocess, unittest, importlib.util
from aide_tests_v2 import dossier_essai, chemin_version, OUTILS

OUTIL = chemin_version('reparer_fragments', 2)
spec = importlib.util.spec_from_file_location('reparer_fragments_essai', OUTIL); RF = importlib.util.module_from_spec(spec); spec.loader.exec_module(RF)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'


class Reparer(unittest.TestCase):
    def ok(self, avant, apres, ori=None):
        r, raison = RF.reparer(avant, ori); self.assertIsNone(raison); self.assertEqual(r, apres)

    def test_sigle_colle(self):
        self.ok('Les 7 éléments listés (), sur 2 pagesEL', 'Les 7 éléments listés (EL), sur 2 pages')
        self.ok('La part des  (5 %) est faible ; les  sont répétés.ELEL', 'La part des EL (5 %) est faible ; les EL sont répétés.')

    def test_fragment_colle_apres_un_point(self):
        self.ok('Tableau 4 (source : classeur).  ; catégorie Y : 5 niveaux. Les valeurs élevées sont signalées.Catégorie X : 3 niveaux',
                'Tableau 4 (source : classeur). Catégorie X : 3 niveaux ; catégorie Y : 5 niveaux. Les valeurs élevées sont signalées.')
        self.ok('Deux variables (la catégorie X,  ; la catégorie Y, détaillé) sont testées.à quatre modalités',
                'Deux variables (la catégorie X, à quatre modalités ; la catégorie Y, détaillé) sont testées.')

    def test_derniere_phrase_sans_ponctuation(self):
        self.ok('Sur cette série, , mais elle reste fragile. la correction réduit l’écart', 'Sur cette série, la correction réduit l’écart, mais elle reste fragile.')
        self.ok('Le module corrige le décalage [9]. , il subit la même variation. Le module corrige aussi la marge : ayant les mêmes propriétés',
                'Le module corrige le décalage [9]. Le module corrige aussi la marge : ayant les mêmes propriétés, il subit la même variation.')

    def test_trou_en_debut(self):
        self.ok(' au tableau final ; la suite viendra plus tard.Non exploitée ici : l’étape a été exercée, et le chapitre s’arrête',
                'Non exploitée ici : l’étape a été exercée, et le chapitre s’arrête au tableau final ; la suite viendra plus tard.')

    def test_refus(self):
        self.assertEqual(RF.reparer('Les  et les  sont là.EL')[1], '1 fragment(s) pour 2 trou(s)')
        self.assertEqual(RF.reparer('Une phrase complète, sans défaut.')[1], 'aucun fragment de fin')
        self.assertEqual(RF.reparer('Les  (n = 3) ont été vus.EL', ori='Les  (n = 3) ont été vus.')[1], 'aucun trou')   # trou d'origine
        self.assertEqual(RF.fragments('Voir le classeur data.xlsx et la feuille 2.1_EL.')[1], [])


def p(pid, ins):
    return f'<w:p w14:paraId="{pid}"><w:r><w:t xml:space="preserve">Base. </w:t></w:r><w:ins w:id="1" w:author="Passe"><w:r><w:t xml:space="preserve">{ins}</w:t></w:r></w:ins></w:p>'


class Module(unittest.TestCase):
    def test_ops_et_apercu(self):
        d = dossier_essai('reparer_fragments'); f = os.path.join(d, 'rapport_v1.docx')
        with zipfile.ZipFile(f, 'w') as z:
            z.writestr('word/document.xml', f'<w:document {W}><w:body>{p("0000000A", "Les éléments listés (), sur 2 pagesEL")}{p("0000000B", "Rien à réparer.")}</w:body></w:document>')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        r = subprocess.run([sys.executable, OUTIL, f, os.path.join(d, 'sortie')], capture_output=True, text=True, env=env); self.assertEqual(r.returncode, 0, r.stderr)
        ns = {}
        with open(os.path.join(d, 'sortie', 'ops_DR09_fragments_v1.py'), encoding='utf-8') as g: exec(g.read(), ns)
        self.assertEqual(len(ns['OPS']), 1); o = ns['OPS'][0]
        self.assertEqual((o['type'], o['cible']), ('remplacer', '0000000A'))
        self.assertEqual(o['couples'][0][1], 'Base. Les éléments listés (EL), sur 2 pages')
        self.assertTrue(os.path.exists(os.path.join(d, 'sortie', 'apercu_ops_DR09_fragments_v1.md')))
        self.assertEqual(subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=env).returncode, 2)


if __name__ == '__main__':
    unittest.main()
