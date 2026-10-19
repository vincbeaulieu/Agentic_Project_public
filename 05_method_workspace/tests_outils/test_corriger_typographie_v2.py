"""Tests de corriger_typographie_v2 : double espace entre deux mots, espace avant « , » et « . », espace manquante avant « ; ? ! : »
(caractère d'espace usuel du document) ; zones protégées (URL, DOI, heures, ratios, fichiers, renvois §, nombres décimaux, tabulations) ;
module d'opérations et aperçu sur un docx d'essai, couverture et section Références écartées, sans nouvelle version si rien ne change."""
import os, sys, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS

CT = importer_version('corriger_typographie', 2); OUTIL = chemin_version('corriger_typographie', 2)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'


class Corriger(unittest.TestCase):
    def test_espaces(self):
        self.assertEqual(CT.corriger('sur six jours.  Le Tableau 1'), 'sur six jours. Le Tableau 1')
        self.assertEqual(CT.corriger('au sens du terme . Plusieurs choix'), 'au sens du terme. Plusieurs choix')
        self.assertEqual(CT.corriger('les éléments , puis'), 'les éléments, puis')
        self.assertEqual(CT.corriger('la différence de format; ou un effet'), 'la différence de format ; ou un effet')
        self.assertEqual(CT.corriger('Points ouverts:  il reste'), 'Points ouverts : il reste')
        self.assertEqual(CT.corriger('Pourquoi?'), 'Pourquoi ?')
        self.assertEqual(CT.corriger('stable ; ', esp=' '), 'stable ; ')                 # déjà espacé : rien
        self.assertEqual(CT.corriger('stable; fin', esp=' '), 'stable ; fin')

    def test_zones_protegees(self):
        for t in ('voir https://doi.org/10.1/x:y et doi: 10.1000/x1', 'à 10:30 puis 14:05', 'un ratio 1:1', 'le fichier data.xlsx', 'valeur .5 et 0,5',
                  'Colonne\t\tB', 'renvoi §A.3.6'):
            self.assertEqual(CT.corriger(t), t, t)

    def test_espace_usuelle(self):
        self.assertEqual(CT.espace_usuelle(['a : b', 'c ; d', 'e : f']), ' ')
        self.assertEqual(CT.espace_usuelle([]), ' ')


def p(pid, texte):
    return f'<w:p w14:paraId="{pid}"><w:r><w:t xml:space="preserve">{texte}</w:t></w:r></w:p>'


class Module(unittest.TestCase):
    def test_ops_et_apercu(self):
        d = dossier_essai('corriger_typographie'); f = os.path.join(d, 'rapport_v1.docx')
        corps = p('00000001', 'Couverture  avec  espaces') + ''.join(p(f'000000{k:02d}', f'Paragraphe {k} normal.') for k in (2, 3)) + \
            p('0000000A', 'Le texte.  Une suite , ici') + p('0000000B', 'Rien à corriger.') + ('<w:p w14:paraId="0000000C"><w:r><w:t xml:space="preserve">La somme est resserrée sur les </w:t></w:r>'
               '<w:del w:id="5" w:author="Passe"><w:r><w:delText>EL</w:delText></w:r></w:del><w:r><w:t xml:space="preserve">, dans les blocs.</w:t></w:r></w:p>')
        with zipfile.ZipFile(f, 'w') as z: z.writestr('word/document.xml', f'<w:document {W}><w:body>{corps}</w:body></w:document>')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        r = subprocess.run([sys.executable, OUTIL, f, os.path.join(d, 'sortie'), '--couverture', '1'], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        ns = {}
        with open(os.path.join(d, 'sortie', 'ops_typographie_v1.py'), encoding='utf-8') as g: exec(g.read(), ns)
        self.assertEqual([o['cible'] for o in ns['OPS']], ['0000000A'])                     # couverture et paragraphe à trou écartés
        self.assertIn('trou laissé par une révision', open(os.path.join(d, 'sortie', 'apercu_ops_typographie_v1.md'), encoding='utf-8').read())
        self.assertEqual(ns['OPS'][0]['couples'][0][1], 'Le texte. Une suite, ici')
        self.assertTrue(os.path.exists(os.path.join(d, 'sortie', 'apercu_ops_typographie_v1.md')))
        subprocess.run([sys.executable, OUTIL, f, os.path.join(d, 'sortie'), '--couverture', '1'], capture_output=True, text=True, env=env)
        self.assertFalse(os.path.exists(os.path.join(d, 'sortie', 'ops_typographie_v2.py')))   # contenu identique : pas de nouvelle version
        self.assertEqual(subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=env).returncode, 2)


if __name__ == '__main__':
    unittest.main()
