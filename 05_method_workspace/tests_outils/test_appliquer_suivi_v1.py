"""Tests de appliquer_suivi_v1 (docx synthétique écrit avec zipfile, module d'opérations écrit dans le dossier d'essai) :
remplacement tolérant (insécable, apostrophe typographique ; « introuvable », « ambigu ») ; ligne de commande nominale
(remplacer, inserer_apres, inserer_apres sur une clé « N:… », réponse à un fil) : suivi sous l'auteur donné, ordre des
paragraphes insérés, journal JSON ; révision d'un autre auteur jamais modifiée de l'intérieur ; échec explicite
« ÉCHEC <id> », code 2, sans aucune sortie, pour un paraId inconnu, un type inconnu, un texte introuvable, un fil inconnu ;
sortie existante refusée sans écrasement ; appel sans argument (défaut signalé : pas de message d'usage)."""
import os, sys, json, zipfile, subprocess, unittest
from lxml import etree
from aide_tests_v2 import dossier_essai, chemin_version, importer_version, OUTILS

OUTIL = chemin_version('appliquer_suivi', 1)
AS = importer_version('appliquer_suivi', 1)
WN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
W15 = 'http://schemas.microsoft.com/office/word/2012/wordml'
NS = (f'xmlns:w="{WN}" xmlns:w14="{W14}" xmlns:w15="{W15}" xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid" '
      'xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"')
D = '2026-01-01T00:00:00Z'
CORPS = ('<w:p w14:paraId="0000000A"><w:commentRangeStart w:id="0"/><w:r><w:t xml:space="preserve">Le chat dort.</w:t></w:r><w:commentRangeEnd w:id="0"/>'
         '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r></w:p>'
         '<w:p w14:paraId="0000000B"><w:r><w:t>Fin.</w:t></w:r></w:p>'
         f'<w:p w14:paraId="0000000C"><w:r><w:t xml:space="preserve">Une voiture </w:t></w:r><w:ins w:id="5" w:author="Collègue A" w:date="{D}"><w:r><w:t>rouge</w:t></w:r></w:ins>'
         '<w:r><w:t xml:space="preserve"> roule vite.</w:t></w:r></w:p>')


def q(t, ns=WN): return '{%s}%s' % (ns, t)


def ecrire_docx(f):
    with zipfile.ZipFile(f, 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr('word/document.xml', f'<w:document {NS}><w:body>{CORPS}</w:body></w:document>')
        z.writestr('word/comments.xml', f'<w:comments {NS}><w:comment w:id="0" w:author="Collègue A" w:date="{D}" w:initials="CA"><w:p w14:paraId="0000C001"><w:r><w:t>Question ?</w:t></w:r></w:p></w:comment></w:comments>')
        z.writestr('word/commentsExtended.xml', f'<w15:commentsEx {NS}><w15:commentEx w15:paraId="0000C001" w15:done="0"/></w15:commentsEx>')
        z.writestr('word/commentsIds.xml', f'<w16cid:commentsIds {NS}><w16cid:commentId w16cid:paraId="0000C001" w16cid:durableId="0000D001"/></w16cid:commentsIds>')
        z.writestr('word/commentsExtensible.xml', f'<w16cex:commentsExtensible {NS}><w16cex:commentExtensible w16cex:durableId="0000D001" w16cex:dateUtc="{D}"/></w16cex:commentsExtensible>')
        z.writestr('word/people.xml', f'<w15:people {NS}></w15:people>')


def lancer(nom, module, *options):
    """Écrit le docx et le module d'opérations dans un dossier d'essai, lance l'outil ; rend (résultat, dossier)."""
    d = dossier_essai('appliquer_suivi_' + nom); ecrire_docx(os.path.join(d, 'entree_v1.docx'))
    with open(os.path.join(d, f'ops_{nom}.py'), 'w', encoding='utf-8') as g: g.write(module)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS, d]))
    r = subprocess.run([sys.executable, OUTIL, f'ops_{nom}', os.path.join(d, 'entree_v1.docx'), os.path.join(d, 'sortie_v1.docx'),
                        os.path.join(d, 'journal_v1.json'), '--auteur', 'Collègue B', '--initiales', 'CB', *options],
                       capture_output=True, text=True, env=env, timeout=120)
    return r, d


def partie(d, nom):
    return etree.fromstring(zipfile.ZipFile(os.path.join(d, 'sortie_v1.docx')).read(nom))


def texte_vu(e, balise='t'):
    return ''.join(t.text or '' for t in e.iter(q(balise)))


class RemplacementTolerant(unittest.TestCase):
    def test_insecable_et_apostrophe(self):
        self.assertEqual(AS.remplacer_tolerant('Le chat dort.', 'Le chat', 'Un chien'), 'Un chien dort.')
        self.assertEqual(AS.remplacer_tolerant('Sous l’arbre.', "l'arbre", 'le chêne'), 'Sous le chêne.')
        with self.assertRaisesRegex(ValueError, 'introuvable'): AS.remplacer_tolerant('Le chat dort.', 'chien', 'x')
        with self.assertRaisesRegex(ValueError, 'ambigu'): AS.remplacer_tolerant('un chat, un chat', 'chat', 'x')


class LigneDeCommande(unittest.TestCase):
    def test_nominal_suivi_journal_reponse(self):
        r, d = lancer('nominal', "OPS = [dict(id='O1', type='remplacer', cible='0000000A', couples=[('chat', 'chien')], point='P1'),\n"
                                 "       dict(id='O2', type='inserer_apres', ref='0000000B', texte='Un.', cle='k'),\n"
                                 "       dict(id='O3', type='inserer_apres', ref='N:k', texte='Deux.')]\n"
                                 "POINTS = ['P1']\nREPONSES = {0: 'Réponse.'}\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn('3 opérations, 1 réponses', r.stdout)
        doc = partie(d, 'word/document.xml'); ps = list(doc.iter(q('p')))
        self.assertEqual([texte_vu(p) for p in ps], ['Le chien dort.', 'Fin.', 'Un.', 'Deux.', 'Une voiture rouge roule vite.'])
        self.assertEqual([texte_vu(e, 'delText') for e in doc.iter(q('del'))], ['chat'])
        self.assertEqual({e.get(q('author')) for e in doc.iter(q('del'))}, {'Collègue B'})
        ins_b = [e for e in doc.iter(q('ins')) if e.get(q('author')) == 'Collègue B']
        self.assertEqual(sorted(texte_vu(e) for e in ins_b if e.getparent().tag != q('rPr')), ['Deux.', 'Un.', 'chien'])
        self.assertEqual(sum(e.getparent().tag == q('rPr') for e in ins_b), 2)   # marques des deux paragraphes insérés
        j = json.load(open(os.path.join(d, 'journal_v1.json'), encoding='utf-8'))
        self.assertEqual((j['auteur'], j['n_points'], [o['id'] for o in j['operations']]), ('Collègue B', 1, ['O1', 'O2', 'O3']))
        self.assertEqual((j['operations'][0]['avant'], j['operations'][0]['apres'], j['operations'][0]['point']), ('Le chat dort.', 'Le chien dort.', 'P1'))
        self.assertEqual(j['cles']['k'], j['operations'][1]['paraId']); self.assertEqual(j['operations'][2]['ref'], j['cles']['k'])
        self.assertEqual(j['reponses'], [dict(fil='0', id=1, texte='Réponse.')])
        com = [c for c in partie(d, 'word/comments.xml').iter(q('comment')) if c.get(q('id')) == '1'][0]
        self.assertEqual((com.get(q('author')), com.get(q('initials')), texte_vu(com)), ('Collègue B', 'CB', 'Réponse.'))
        parents = [c.get(q('paraIdParent', W15)) for c in partie(d, 'word/commentsExtended.xml').iter(q('commentEx', W15))]
        self.assertEqual(parents, [None, '0000C001'])
        self.assertEqual([e.get(q('id')) for e in doc.iter(q('commentReference'))], ['0', '1'])

    def test_revision_d_un_autre_auteur_preservee(self):
        r, d = lancer('autre_auteur', "OPS = [dict(id='O1', type='remplacer', cible='0000000C', couples=[('voiture', 'auto'), ('vite', 'lentement')])]\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a = [e for e in partie(d, 'word/document.xml').iter(q('ins')) if e.get(q('author')) == 'Collègue A']
        self.assertEqual([(e.get(q('id')), e.get(q('date')), texte_vu(e)) for e in a], [('5', D, 'rouge')])
        r, d = lancer('autre_auteur_suppr', "OPS = [dict(id='O1', type='remplacer', cible='0000000C', couples=[('rouge', 'bleue')])]\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a = [e for e in partie(d, 'word/document.xml').iter(q('ins')) if e.get(q('author')) == 'Collègue A'][0]
        self.assertEqual((a.get(q('id')), texte_vu(a), texte_vu(a, 'delText')), ('5', '', 'rouge'))   # suppression imbriquée dans l'insertion de A
        self.assertEqual(a.find(q('del')).get(q('author')), 'Collègue B')

    def test_paraid_inconnu(self):
        r, d = lancer('inconnu', "OPS = [dict(id='O1', type='remplacer', cible='0000000A', couples=[('chat', 'chien')]),\n"
                                 "       dict(id='O9', type='inserer_apres', ref='DEADBEEF', texte='Perdu.')]\n")
        self.assertEqual(r.returncode, 2); self.assertIn('ÉCHEC O9', r.stdout); self.assertIn('paraId inconnu : DEADBEEF', r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, 'sortie_v1.docx'))); self.assertFalse(os.path.exists(os.path.join(d, 'journal_v1.json')))

    def test_autres_echecs_explicites(self):
        for nom, module, attendu in [
                ('type', "OPS = [dict(id='R6', type='fusionner', cible='0000000B')]\n", 'ÉCHEC R6 : type inconnu : fusionner'),
                ('introuvable', "OPS = [dict(id='R7', type='remplacer', cible='0000000B', couples=[('Début', 'x')])]\n", 'ÉCHEC R7 : introuvable'),
                ('cle', "OPS = [dict(id='R8', type='inserer_apres', ref='N:absente', texte='x')]\n", 'ÉCHEC R8'),
                ('fil', "OPS = []\nREPONSES = {99: 'x'}\n", 'ÉCHEC réponse 99')]:
            with self.subTest(nom):
                r, d = lancer('echec_' + nom, module)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr); self.assertIn(attendu, r.stdout)
                self.assertFalse(os.path.exists(os.path.join(d, 'sortie_v1.docx')))

    def test_sortie_existante_non_ecrasee(self):
        d = dossier_essai('appliquer_suivi_existe'); ecrire_docx(os.path.join(d, 'entree_v1.docx'))
        with open(os.path.join(d, 'ops_existe.py'), 'w', encoding='utf-8') as g: g.write("OPS = []\n")
        with open(os.path.join(d, 'sortie_v1.docx'), 'w', encoding='utf-8') as g: g.write('ancienne version')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS, d]))
        r = subprocess.run([sys.executable, OUTIL, 'ops_existe', os.path.join(d, 'entree_v1.docx'), os.path.join(d, 'sortie_v1.docx'),
                            os.path.join(d, 'journal_v1.json')], capture_output=True, text=True, env=env, timeout=120)
        self.assertNotEqual(r.returncode, 0); self.assertIn('existe déjà', r.stderr)
        self.assertEqual(open(os.path.join(d, 'sortie_v1.docx'), encoding='utf-8').read(), 'ancienne version')
        self.assertFalse(os.path.exists(os.path.join(d, 'journal_v1.json')))

    def test_sans_argument_refuse(self):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        self.assertNotEqual(subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=env, timeout=120).returncode, 0)

    @unittest.expectedFailure
    def test_sans_argument_message_usage(self):
        # Défaut : sans argument, l'outil s'arrête sur une trace « ValueError: not enough values to unpack » (code 1)
        # au lieu d'afficher son USAGE avec un code 2.
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(OUTILS, '_compat'), OUTILS]))
        r = subprocess.run([sys.executable, OUTIL], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 2); self.assertIn('USAGE', (r.stdout + r.stderr).upper()); self.assertNotIn('Traceback', r.stderr)


if __name__ == '__main__':
    unittest.main()
