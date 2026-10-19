"""Tests de verifier_citations_v1 (outil promu du script de projet verifier_citations_v6) : cas justes acceptés, cas faux rejetés,
chaque défaut étant prouvé présent dans sa fixture (LC-032) ; absence écrite en regex vraiment cherchée (défaut de la v5 du script :
elle passait toujours) ; image et preuve hors texte ; appels invalides refusés bruyamment ; JSON jamais écrasé ; ligne de commande.
Contrôle de non-régression : sur les jugements réels du dossier 17 (s'ils sont présents), même bilan que le script de projet v6."""
import os, sys, json, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version, importer_version

OUTIL = chemin_version('verifier_citations', 1)
V = importer_version('verifier_citations', 1)
TEXTE = ('AAAA0001\t \t1 Intro\tLes lignes vues sont notées sur la page B.\n'
         'AAAA0002\t \t2 Suite\tAucun brouillon ici ;\tComment lire une performance.\n'
         'AAAA0003\t \t3 Fin\tUne citation « imbriquée » dans le texte.\n')
BASE = dict(fil='X', verdict='traité', motif='', manque='')


class Verification(unittest.TestCase):
    def setUp(self):
        self.d = dossier_essai('verifier_citations_v1')
        self.ref = os.path.join(self.d, 'texte.txt'); open(self.ref, 'x', encoding='utf-8').write(TEXTE)
        os.makedirs(os.path.join(self.d, 'img')); open(os.path.join(self.d, 'img', 'f1.png'), 'xb').write(b'png')
        self.n = 0

    def lance(self, j, *opts):
        self.n += 1; f = os.path.join(self.d, f'j{self.n}.json'); open(f, 'x', encoding='utf-8').write(json.dumps([j], ensure_ascii=False))
        r = subprocess.run([sys.executable, OUTIL, self.ref, f, '--racine', self.d, *opts], capture_output=True, text=True)
        return r.returncode, r.stdout

    def test_justes(self):
        for j in (dict(BASE, preuve='« lignes vues » (¶AAAA0001)'),
                  dict(BASE, preuve='« Les lignes … page B » (¶AAAA0001)'),
                  dict(BASE, preuve='« Comment lire une performance » (¶AAAA0002)'),          # texte après une tabulation
                  dict(BASE, preuve='« Une citation « imbriquée » dans » (¶AAAA0003)'),
                  dict(BASE, preuve='', absent=['(?i)LIGNES? ABSENTES?']),
                  dict(BASE, preuve='', absent=['lignes absentes']),
                  dict(BASE, preuve='image', verif_image='img/f1.png'),
                  dict(BASE, preuve='hors texte', verif_hors_texte='docx : 0 commentaire'),
                  dict(BASE, verdict='non traité', preuve='')):
            c, out = self.lance(j)
            self.assertEqual(c, 0, (j, out))

    def test_faux(self):
        self.assertIn('lignes vues', TEXTE.lower()); self.assertIn('comment lire', TEXTE.lower())   # défauts présents
        for j, attendu in ((dict(BASE, preuve='« lignes perdues » (¶AAAA0001)'), 1),
                           (dict(BASE, preuve='« lignes vues » (¶AAAA0009)'), 1),
                           (dict(BASE, preuve='« page B … lignes » (¶AAAA0001)'), 1),             # ordre inversé
                           (dict(BASE, preuve='« x » (¶AAAA0001)', absent=['(?i)LIGNES VUES']), 1),
                           (dict(BASE, preuve='« x » (¶AAAA0001)', absent=['(?i)comment lire']), 1),
                           (dict(BASE, preuve='image', verif_image='img/absente.png'), 1),
                           (dict(BASE, verdict='traité ?', preuve='« lignes vues » (¶AAAA0001)'), 1),
                           (dict(BASE, preuve='rien de vérifiable'), 2)):
            c, out = self.lance(j)
            self.assertEqual(c, attendu, (j, out))

    def test_regex_vraiment_cherchee(self):
        T = V.lire_reference(self.ref)
        b, _ = V.verifier(T, [('j', [dict(BASE, preuve='', absent=['(?i)brouillon'])])])
        self.assertEqual(b['echecs'], 1)                      # « brouillon » est dans le texte : l'absence est fausse
        b, _ = V.verifier(T, [('j', [dict(BASE, preuve='', absent=['(?i)brouillons? final'])])])
        self.assertEqual(b['echecs'], 0)

    def test_appels_invalides(self):
        f = os.path.join(self.d, 'ok.json'); open(f, 'x', encoding='utf-8').write(json.dumps([dict(BASE, preuve='« lignes vues » (¶AAAA0001)')]))
        vide = os.path.join(self.d, 'vide.txt'); open(vide, 'x', encoding='utf-8').write('rien\n')
        pasliste = os.path.join(self.d, 'pasliste.json'); open(pasliste, 'x', encoding='utf-8').write('{}')
        for args in ([self.ref], [self.ref, os.path.join(self.d, 'absent.json')], [vide, f], [self.ref, pasliste], [self.ref, f, '--json']):
            r = subprocess.run([sys.executable, OUTIL, *args], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, (args, r.stdout))

    def test_json_jamais_ecrase(self):
        f = os.path.join(self.d, 'ok.json'); open(f, 'x', encoding='utf-8').write(json.dumps([dict(BASE, preuve='« lignes vues » (¶AAAA0001)')]))
        s = os.path.join(self.d, 'sortie.json')
        r = subprocess.run([sys.executable, OUTIL, self.ref, f, '--json', s], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout); self.assertEqual(json.load(open(s))['conformes'], 1)
        r = subprocess.run([sys.executable, OUTIL, self.ref, f, '--json', s], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


D17 = '/home/claude/17_comparaison_v6.0.4'


@unittest.skipUnless(os.path.isfile(os.path.join(D17, '90_scripts', 'verifier_citations_v6.py')), 'dossier 17 absent de cet espace')
class NonRegression(unittest.TestCase):
    def test_meme_bilan_que_le_script_v6(self):
        ref = os.path.join(D17, '01_dossiers', 'textes', 'texte_v6.0.12-rev1_v2.txt')
        J = [os.path.join(D17, '02_jugements', 'moi', n) for n in ('jugements_fils_p1_v3.json', 'jugements_fils_p2_v6.json', 'jugements_reperes_r3_v3.json')]
        if not all(os.path.isfile(x) for x in J): self.skipTest('jugements révisés absents')
        a = subprocess.run([sys.executable, os.path.join(D17, '90_scripts', 'verifier_citations_v6.py'), ref, *J, '--racine', D17], capture_output=True, text=True)
        b = subprocess.run([sys.executable, OUTIL, ref, *J, '--racine', D17], capture_output=True, text=True)
        self.assertEqual(a.returncode, b.returncode)
        n = lambda s: [l for l in s.splitlines() if l.startswith('ÉCHEC')]
        self.assertEqual(n(a.stdout), n(b.stdout))
        self.assertEqual(a.stdout.split('Citations vérifiées : ')[1].split(' ')[0], b.stdout.split('Preuves vérifiées : ')[1].split(' ')[0])


if __name__ == '__main__':
    unittest.main()
