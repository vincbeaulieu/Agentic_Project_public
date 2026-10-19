"""Suite v2 (16 oct. 2026) : copie de la v1, qui s'appuie sur test_tableau_de_bord_v3. Tests de serveur_tableau_de_bord_v1 (PowerShell) et de son lanceur, sur un dossier Revision fictif (dossier_essai).
Le serveur tourne sous PowerShell 7 (pwsh) quand il est présent ; sinon les tests sont sautés (sur le PC, PowerShell 5.1 le lance).
Testé :
- /api/ping, page servie complète (doctype, titre dans l'en-tête, données intégrées), 404 et 405 ;
- /api/brut : mêmes enregistrements que « tableau_de_bord brut » (Python), par paquets (curseur, MaxEvenements), fichiers
  d'état envoyés seulement quand leur signature change, fichier trop récent (< 2 s) remis au passage suivant ;
- registre des chemins : dossiers renommés lus par le serveur ;
- bout en bout : les fichiers servis, agrégés par la page (Node), redonnent exactement collecter() ;
- navigateur (Chromium, si Playwright est présent) : passage en direct, bascule FR / EN, nouvel événement affiché sans recharger ;
- lanceur .cmd : ASCII, fins de ligne Windows, dernière version du serveur.
Écritures : sous dossier_essai seulement."""
import os, sys, re, json, time, glob, socket, shutil, subprocess, unittest, urllib.request, urllib.error, urllib.parse
from aide_tests_v2 import dossier_essai, chemin_version, chemin
import cc_lib_v4 as L4
import test_tableau_de_bord_v3 as T1   # v2 : suite v1 rendue indépendante de la date

SERVEUR = chemin_version('serveur_tableau_de_bord', 1, 'ps1')
LANCEUR = chemin_version('lancer_tableau_de_bord', 1, 'cmd')
TABLEAU = chemin_version('tableau_de_bord', 2)
PWSH = shutil.which('pwsh') or ('/opt/pwsh/pwsh' if os.path.exists('/opt/pwsh/pwsh') else None)
NODE = shutil.which('node')
PASSE = 1700000000                                    # date de fichier ancienne (évite la garde des fichiers en cours d'écriture)


def port_libre():
    with socket.socket() as s: s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


def vieillir(racine):
    for f in glob.glob(os.path.join(racine, '**', '*'), recursive=True):
        if os.path.isfile(f): os.utime(f, (PASSE, PASSE))


@unittest.skipUnless(PWSH, 'PowerShell (pwsh) absent')
class Serveur(unittest.TestCase):
    renommer = False
    agents_fictifs = classmethod(T1.Base.agents_fictifs)       # réutilisés de la suite v1 (n'utilisent que cc)

    @classmethod
    def setUpClass(cls):
        cls.rev = dossier_essai('serveur_tableau_de_bord_v1' + ('_renomme' if cls.renommer else ''))
        cls.cc = os.path.join(cls.rev, '00_competences_claude'); os.makedirs(cls.cc)
        if cls.renommer:
            T1.w(os.path.join(cls.cc, 'outils', '_gestion', 'chemins_v1.json'),
                 json.dumps(dict(chemins={k: v + '_renomme' for k, v in T1.chemins(cls.cc).items() if k != 'outils'})))
        cls._sauve = (L4.RACINE_CC, os.environ.get('CC_BANC'), T1.CANDIDAT); L4.RACINE_CC = cls.cc; os.environ.pop('CC_BANC', None)
        T1.CANDIDAT = TABLEAU; cls.TB = T1.charger(cls.cc)
        g = T1.Generation.preparer.__get__(cls); src, _ = g(); cls.TB.maj_agents([src])
        F = os.path.join(cls.rev, '00_espace_cloud_claude', 'file_lmstudio')
        T1.w(os.path.join(F, 'journal', 'etat.json'), json.dumps(dict(statut='arrêté', raison_arret='file vide', traites=2)))
        T1.w(os.path.join(F, 'entree', 'lot_a.jsonl'), '{}\n')
        cls.main(cls, 'generer', '--sans-agents')
        vieillir(cls.rev)
        cls.port = port_libre(); cls.base = f'http://127.0.0.1:{cls.port}'
        cls.p = subprocess.Popen([PWSH, '-NoProfile', '-File', SERVEUR, '-Racine', cls.cc, '-Port', str(cls.port), '-SansNavigateur',
                                  '-DureeMax', '240', '-MaxEvenements', '4'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(200):
            try:
                if json.loads(cls.get(cls, '/api/ping')[1])['ok']: break
            except (OSError, ValueError): time.sleep(0.1)
        else: raise RuntimeError('serveur injoignable')

    @classmethod
    def tearDownClass(cls):
        cls.p.terminate()
        try: cls.p.wait(10)
        except subprocess.TimeoutExpired: cls.p.kill()
        L4.RACINE_CC = cls._sauve[0]; T1.CANDIDAT = cls._sauve[2]
        if cls._sauve[1] is not None: os.environ['CC_BANC'] = cls._sauve[1]

    def main(self, *a):
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out): return self.TB.main(list(a)), out.getvalue()

    def get(self, chemin_, methode='GET'):
        rq = urllib.request.Request(self.base + chemin_, method=methode)
        try:
            with urllib.request.urlopen(rq, timeout=30) as r: return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e: return e.code, e.read().decode('utf-8')

    def tout_brut(self, sig=''):
        """Toutes les pages de /api/brut depuis le début : (enregistrements E, F, nombre d'appels, dernière méta)."""
        cur, E, F, n = '', [], {}, 0
        while True:
            code, txt = self.get(f'/api/brut?apres={urllib.parse.quote(cur)}&sig={sig}'); self.assertEqual(code, 200, txt); n += 1
            L = [l for l in txt.split('\n') if l]; meta = json.loads(L[0].split('\t', 1)[1]); self.assertEqual(L[0][:2], 'M\t')
            for l in L[1:]:
                p = l.split('\t')
                if p[0] == 'E': E.append((p[1], json.loads(p[2])))
                elif p[0] == 'F': F[p[1]] = (p[2], json.loads(p[3]))
            cur = meta['curseur']
            if meta['fin']: return E, F, n, meta
            self.assertLessEqual(len([l for l in L if l.startswith('E')]), 4)

    def brut_python(self):
        f = os.path.join(self.cc, f'brut_{time.time_ns()}.txt'); self.main('brut', '--sortie', f)
        L = [l for l in open(f, encoding='utf-8').read().split('\n') if l]
        E = [(l.split('\t')[1], json.loads(l.split('\t')[2])) for l in L if l.startswith('E\t')]
        F = {l.split('\t')[1]: (l.split('\t')[2], json.loads(l.split('\t')[3])) for l in L if l.startswith('F\t')}
        return E, F, f

    def test_ping_et_page(self):
        code, t = self.get('/api/ping'); self.assertEqual((code, json.loads(t)['serveur']), (200, 'serveur_tableau_de_bord'))
        code, page = self.get('/'); self.assertEqual(code, 200)
        self.assertTrue(page.startswith('<!doctype html>'))
        self.assertLess(page.index('<title>Tableau de bord du flux</title>'), page.index('</head>'))
        self.assertLess(page.index('<body>'), page.index('<div class="page">'))
        self.assertIn('id="donnees"', page); self.assertIn('data-lang="en"', page)
        self.assertEqual(self.get('/inconnu')[0], 404); self.assertEqual(self.get('/', 'POST')[0], 405)

    def test_brut_par_paquets_identique_a_python(self):
        E, F, n, _ = self.tout_brut(); Ep, Fp, _ = self.brut_python()
        self.assertGreater(n, 1)                                                        # MaxEvenements = 4 : plusieurs appels
        self.assertEqual([k for k, _ in E], [k for k, _ in Ep]); self.assertEqual(E, Ep)
        self.assertEqual(sorted(F), ['agents', 'lmstudio', 'planificateur', 'registre'])
        for k in ('agents', 'planificateur', 'registre'): self.assertEqual(F[k], Fp[k], k)
        self.assertEqual(F['lmstudio'][1], Fp['lmstudio'][1]); self.assertEqual(F['lmstudio'][1]['lots_entree'], 1)

    def test_signature_et_fichier_recent(self):
        _, _, _, meta = self.tout_brut()
        code, t = self.get(f'/api/brut?apres={urllib.parse.quote(meta["curseur"])}&sig={meta["sig"]}')
        self.assertEqual([l[0] for l in t.split('\n') if l], ['M'])                     # rien de neuf : méta seule
        f = self.TB.ecrire_etape('point', 'T-1', note='tout frais', quand='2026-10-15T09:45:00Z')   # écrit à l'instant
        code, t = self.get(f'/api/brut?apres={urllib.parse.quote(meta["curseur"])}&sig={meta["sig"]}')
        self.assertNotIn('tout frais', t); self.assertTrue(json.loads(t.split('\n')[0].split('\t', 1)[1])['fin'])
        os.utime(f, (PASSE, PASSE))
        code, t = self.get(f'/api/brut?apres={urllib.parse.quote(meta["curseur"])}&sig={meta["sig"]}')
        self.assertIn('tout frais', t); self.assertNotIn('\nF\t', t)
        T1.w(chemin('propositions', 'registre_propositions_v2.json', racine=self.cc), json.dumps(dict(propositions={})))
        code, t = self.get(f'/api/brut?apres={urllib.parse.quote(meta["curseur"])}&sig={meta["sig"]}')
        self.assertIn('\nF\tregistre\t', t); self.assertIn('registre_propositions_v2.json', t)

    def test_bout_en_bout_identique_a_collecter(self):
        if not NODE: self.skipTest('Node absent')
        E, F, _, _ = self.tout_brut()
        f = os.path.join(self.cc, f'brut_serveur_{time.time_ns()}.txt')
        with open(f, 'w', encoding='utf-8') as g:
            g.write('M\t{}\n' + ''.join(f'E\t{k}\t{json.dumps(e, ensure_ascii=False)}\n' for k, e in E)
                    + ''.join(f'F\t{k}\t{s}\t{json.dumps(c, ensure_ascii=False)}\n' for k, (s, c) in F.items()))
        page = os.path.join(self.cc, 'page.html'); T1.w(page, self.TB.GABARIT); h = os.path.join(self.cc, 'harnais.js')
        T1.w(h, """const fs = require('fs'); const [, , page, brut] = process.argv; const g = fs.readFileSync(page, 'utf8');
const cron = g.slice(g.indexOf('/*CRON-DEBUT*/'), g.indexOf('/*CRON-FIN*/')), ag = g.slice(g.indexOf('/*AGREGER-DEBUT*/'), g.indexOf('/*AGREGER-FIN*/'));
const f = new Function('texte', 'conf', cron + '\\n' + ag + '\\nconst B = AG.nouveauBrut(); AG.lireBrut(texte, B); conf.analyserCron = analyserCron; return AG.agreger(B, conf);');
process.stdout.write(JSON.stringify(f(fs.readFileSync(brut, 'utf8'), JSON.parse(fs.readFileSync(0, 'utf8')))));""")
        P = json.loads(json.dumps(self.TB.collecter(etat_sync=None)))
        r = subprocess.run([NODE, h, page, f], input=json.dumps(dict(seuils=self.TB.SEUILS, categories=list(self.TB.CATEGORIES), outil=P['outil'])),
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr); J = json.loads(r.stdout)
        for g in P['goulots']:
            for k in ('titre', 'preuve', 'piste'): g.pop(k)
        self.assertEqual(len(P['planificateur'].pop('erreurs')), len(J['planificateur'].pop('erreurs')))
        for k in sorted(set(P) | set(J)): self.assertEqual(P.get(k), J.get(k), k)
        self.assertIn('G-LM1', [g['code'] for g in J['goulots']])

    def test_navigateur_direct_et_langue(self):
        try: from playwright.sync_api import sync_playwright
        except ImportError: self.skipTest('Playwright absent')
        ess = dossier_essai('serveur_tableau_de_bord_v1_navigateur')
        with sync_playwright() as pw:
            nav = pw.chromium.launch(); pg = nav.new_page(viewport=dict(width=1200, height=900))
            pg.route('**/*', lambda r: r.continue_() if r.request.url.startswith(self.base) else r.abort())
            pg.goto(self.base + '/', wait_until='domcontentloaded')
            pg.wait_for_selector('#mode.direct', timeout=20000)
            pg.wait_for_function("document.querySelector('#mode').textContent.indexOf('relu') >= 0", timeout=20000)
            self.assertEqual(pg.inner_text('h1'), 'Tableau de bord du flux')
            pg.screenshot(path=os.path.join(ess, 'direct_fr.png'), full_page=True)
            f = self.TB.ecrire_etape('debut', 'T-direct', titre='Étape vue en direct', categorie='outils', quand='2026-10-15T10:59:00Z'); os.utime(f, (PASSE, PASSE))
            pg.wait_for_function("document.querySelector('#liste-journal').textContent.indexOf('Étape vue en direct') >= 0", timeout=20000)
            pg.click('#langue button[data-lang="en"]')
            self.assertEqual(pg.inner_text('h1'), 'Workflow dashboard')
            self.assertEqual(pg.inner_text('nav.sommaire a[href="#planificateur"]'), 'Scheduler')
            self.assertEqual(pg.evaluate('document.documentElement.lang'), 'en')
            self.assertIn('Live', pg.inner_text('#mode'))
            pg.screenshot(path=os.path.join(ess, 'direct_en.png'), full_page=True)
            pg.reload(wait_until='domcontentloaded'); pg.wait_for_selector('#mode.direct', timeout=20000)
            self.assertEqual(pg.inner_text('h1'), 'Workflow dashboard')                 # langue retenue (stockage du navigateur)
            nav.close()


class ServeurRegistreRenomme(Serveur):
    renommer = True

    def test_dossiers_renommes(self):
        E, F, _, _ = self.tout_brut()
        self.assertTrue(E); self.assertTrue(F['planificateur'][0].startswith(T1.chemins(self.cc)['taches']))
        self.assertTrue(F['planificateur'][0].split('/')[0].endswith('_renomme'))


class Lanceur(unittest.TestCase):
    def test_lanceur(self):
        b = open(LANCEUR, 'rb').read(); b.decode('ascii')
        self.assertIn(b'\r\n', b); self.assertNotIn(b'\n', b.replace(b'\r\n', b''))
        t = b.decode('ascii')
        self.assertIn("serveur_tableau_de_bord_v*.ps1", t); self.assertIn('-ExecutionPolicy Bypass', t)
        self.assertIn('Select-Object -Last 1', t); self.assertIn('pause', t)

    def test_entete_du_serveur(self):
        t = open(SERVEUR, encoding='utf-8').read()
        for k in ('# OUTIL: serveur_tableau_de_bord', '# VERSION: 1', '# USAGE:', '# BANC: tests/test_serveur_tableau_de_bord_v1.py'): self.assertIn(k, t)
        code = [l.split('#', 1)[0] for l in t.split('\n') if not l.lstrip().startswith('#')]
        self.assertEqual([l for l in code if re.search(r'[^\x00-\x7f]', l)], [])      # chaînes ASCII : lues pareil par PowerShell 5.1 sans BOM
        self.assertIn('Loopback', t); self.assertNotIn('IPAddress]::Any', t)


if __name__ == '__main__':
    unittest.main()
