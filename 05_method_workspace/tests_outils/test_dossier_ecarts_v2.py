"""v2 de la suite (détecteurs dans leur version courante). Tests de dossier_ecarts_v2 sur un petit docx en suivi construit pour l'essai : différence mot à mot, informations
vérifiables perdues (renvois, nombres, sigles), meilleure reprise ailleurs ; constitution du dossier groupé par section
(Markdown et JSON versionnés) ; bilan d'un fichier de jugements (conforme, écart non jugé, verdict non permis, sans motif) ;
recherche dans la vue acceptée ou d'origine."""
import os, sys, json, zipfile, subprocess, unittest, importlib.util
from aide_tests_v2 import dossier_essai, chemin_version, OUTILS

OUTIL = chemin_version('dossier_ecarts', 2)
spec = importlib.util.spec_from_file_location('dossier_ecarts_essai', OUTIL); DE = importlib.util.module_from_spec(spec); spec.loader.exec_module(DE)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def p(texte='', style=None, supprime=None, insere=None, com=None):
    pp = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
    c0, c1 = (f'<w:commentRangeStart w:id="{com}"/>', f'<w:commentRangeEnd w:id="{com}"/>') if com else ('', '')
    r = f'<w:r><w:t xml:space="preserve">{texte}</w:t></w:r>' if texte else ''
    if supprime: r += f'<w:del w:id="1" w:author="Correction - Claude"><w:r><w:delText xml:space="preserve">{supprime}</w:delText></w:r></w:del>'
    if insere: r += f'<w:ins w:id="2" w:author="Correction - Claude"><w:r><w:t xml:space="preserve">{insere}</w:t></w:r></w:ins>'
    return f'<w:p>{pp}{c0}{r}{c1}</w:p>'


def docx(chemin):
    corps = ''.join([p('1 Contexte', 'Heading1'),
                     p('', supprime='La série compte 128 mesures et cite [12] pour le test X.', com='5'),
                     p('Texte gardé, sur la série et ses mesures : 128.'),
                     p('2 Méthode', 'Heading1'),
                     p('La méthode ', insere='simplifiée ', com='7'), ])
    with zipfile.ZipFile(chemin, 'w') as z:
        z.writestr('word/document.xml', f'<w:document {W}><w:body>{corps}</w:body></w:document>')
        z.writestr('word/comments.xml', f'<w:comments {W}><w:comment w:id="5" w:author="Auteur"><w:p><w:r><w:t>Reformuler, ne pas supprimer.</w:t></w:r></w:p></w:comment>'
                                        f'<w:comment w:id="7" w:author="Auteur"><w:p><w:r><w:t>Faire plus simple ?</w:t></w:r></w:p></w:comment></w:comments>')


def lancer(*a):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
    r = subprocess.run([sys.executable, OUTIL] + list(a), capture_output=True, text=True, env=env); return r.returncode, r.stdout + r.stderr


class Fonctions(unittest.TestCase):
    def test_differences(self):
        self.assertEqual(DE.differences('a b c', 'a x c'), 'a [-b-] {+x+} c')
        self.assertIn(' … ', DE.differences(' '.join(map(str, range(30))) + ' fin', ' '.join(map(str, range(30)))))

    def test_informations_perdues(self):
        self.assertEqual(DE.perdues('Voir [12], 128 cas, REF-907 et 0,071.', 'Il reste 128 cas.'), ['0,071', 'REF-907', '[12]'])


class Dossier(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('dossier_ecarts'); self.docx = os.path.join(self.d, 'rapport_v1.docx'); docx(self.docx)
        self.cr = os.path.join(self.d, 'croisement_v1.json'); self.mt = os.path.join(self.d, 'mt_v1.jsonl')
        json.dump({'D-1': dict(type='modifier', ancre=dict(index=1, supprime=True), section=dict(nom='1 Contexte'), ecarts=['E1'], priorite=1, statut_annonce='Traité'),
                   'D-2': dict(type='question', ancre=dict(index=4, supprime=False), section=dict(nom='2 Méthode'), ecarts=['E4'], priorite=3, statut_annonce=None),
                   'D-3': dict(type='modifier', ancre=dict(index=2, supprime=False), section=dict(nom='1 Contexte'), ecarts=[], priorite=None, statut_annonce=None)},
                  open(self.cr, 'w', encoding='utf-8'))
        with open(self.mt, 'w', encoding='utf-8') as g:
            for i, f, t in (('D-1', '5', 'Reformuler, ne pas supprimer.'), ('D-2', '7', 'Faire plus simple ?'), ('D-3', None, 'rien')):
                g.write(json.dumps(dict(id=i, fil=f, texte=t)) + '\n')

    def test_constituer_et_bilan(self):
        c, s = lancer('constituer', self.docx, self.cr, self.mt, os.path.join(self.d, 'sortie'), '--codes', 'E1'); self.assertEqual(c, 0, s)
        J = json.load(open(os.path.join(self.d, 'sortie', 'dossier_ecarts_v1.json'), encoding='utf-8'))['demandes']
        self.assertEqual(list(J), ['D-1']); e = J['D-1']
        self.assertEqual(e['acceptee'], ''); self.assertIn('[-La série', e['difference']); self.assertEqual(e['perdues'], ['[12]'])
        self.assertEqual(e['ailleurs']['index'], 2)
        md = open(os.path.join(self.d, 'sortie', 'dossier_ecarts_v1.md'), encoding='utf-8').read()
        self.assertIn('## 1 Contexte (1)', md); self.assertIn('[12]', md)
        c, s = lancer('constituer', self.docx, self.cr, self.mt, os.path.join(self.d, 'sortie'), '--codes', 'E1')     # même contenu : pas de v2
        self.assertFalse(os.path.exists(os.path.join(self.d, 'sortie', 'dossier_ecarts_v2.md')))
        fj = os.path.join(self.d, 'jugements_v1.json')
        json.dump({'D-1': dict(verdict='a_restaurer', motif='suppression au lieu de la reformulation demandée')}, open(fj, 'w', encoding='utf-8'))
        c, s = lancer('bilan', self.cr, fj, '--codes', 'E1'); self.assertEqual(c, 0, s); self.assertIn('BILAN CONFORME', s)
        json.dump({'D-1': dict(verdict='approuve', motif='')}, open(fj, 'w', encoding='utf-8'))
        c, s = lancer('bilan', self.cr, fj, '--codes', 'E1,E4'); self.assertEqual(c, 1)
        for t in ('non jugés : D-2', 'verdict non permis : D-1', 'sans motif : D-1'): self.assertIn(t, s)

    def test_chercher(self):
        c, s = lancer('chercher', self.docx, 'simplifiée'); self.assertIn('¶4', s)
        c, s = lancer('chercher', self.docx, r'\[12\]'); self.assertIn('aucune occurrence', s)
        c, s = lancer('chercher', self.docx, r'\[12\]', '--vue', 'ori'); self.assertIn('¶1', s)
        self.assertEqual(lancer()[0], 2)


if __name__ == '__main__':
    unittest.main()
