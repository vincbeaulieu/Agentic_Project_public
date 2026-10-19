"""v7 de la suite : contre detecteurs_rapport_v7 (dossier des règles par le registre des chemins) ; la comparaison avec la v5, devenue inutilisable après le renommage des dossiers, est retirée. Tests de detecteurs_rapport_v7 (DR-09 étendu) sur un docx d'essai en suivi : « trou de ponctuation » et « mot collé après
un point » (mot d'une lettre ou à majuscule) signalés quand la révision les crée, pas quand ils existaient déjà dans la vue
d'origine ; la v5 ne les voyait pas (raison de la nouvelle version) ; noms de fichiers non signalés."""
import os, sys, json, zipfile, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, OUTILS

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def par(fixe, ins=''):
    r = f'<w:r><w:t xml:space="preserve">{fixe}</w:t></w:r>'
    if ins: r += f'<w:ins w:id="1" w:author="Passe"><w:r><w:t xml:space="preserve">{ins}</w:t></w:r></w:ins>'
    return f'<w:p>{r}</w:p>'


def dr09(version, f):
    j = f + f'.v{version}.json'; env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
    r = subprocess.run([sys.executable, chemin_version('detecteurs_rapport', version), f, '--json', j], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    with open(j, encoding='utf-8') as g: return [c for c in json.load(g)['constats'] if c['regle'] == 'DR-09']


class DR09(unittest.TestCase):
    def setUp(self):
        d = dossier_essai('detecteurs_v6'); self.f = os.path.join(d, 'essai_v1.docx')
        corps = ''.join([par('Deux variables (la catégorie X, ', ' ; la catégorie Y) sont testées.à quatre modalités'),
                         par('Les valeurs ne peuvent plus être séparées.', 'Catégorie X : 3 niveaux'),
                         par('Texte déjà ainsi dans l’origine , ; sans révision.'),
                         par('Voir le classeur ', 'data.xlsx et la feuille finale.')])
        with zipfile.ZipFile(self.f, 'w') as z: z.writestr('word/document.xml', f'<w:document {W}><w:body>{corps}</w:body></w:document>')

    def test_nouveaux_motifs(self):
        D = dr09(7, self.f); txt = ' | '.join(c['detail'] for c in D)
        self.assertIn('trou de ponctuation', txt); self.assertIn('testées.à', txt); self.assertIn('séparées.Catégorie', txt)
        self.assertEqual({c['index'] for c in D}, {0, 1})                       # ni l'origine (¶2) ni le nom de fichier (¶3)


if __name__ == '__main__':
    unittest.main()
