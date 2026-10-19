"""Tests de lancer_worker_lmstudio_v4 (lanceur .cmd de l'ouvrier LM Studio).
La partie PowerShell du lanceur (recherche de l'ouvrier installé) est exécutée sous pwsh, dans un dossier Revision fictif, à la place
de cmd.exe : %~dp0 est remplacé par le dossier du lanceur. Testé :
- lancé depuis outils\\lancer_worker_lmstudio\\ : démarre la dernière version installée (v10 avant v3 : tri numérique) ;
- lancé depuis le dossier d'installation : démarre l'ouvrier voisin ;
- la copie source (outils\\worker_lmstudio\\) n'est jamais lancée ; sans installation : code 5 et message clair ;
- fichier : ASCII, fins de ligne Windows, en-tête complet, aucune version d'ouvrier écrite en dur.
La recette finale (double-clic sous Windows, PowerShell 5.1) se fait sur le PC : voir le guide de livraison vérifiée."""
import os, re, shutil, subprocess, unittest
from aide_tests_v2 import dossier_essai, chemin_version

LANCEUR = chemin_version('lancer_worker_lmstudio', 4, 'cmd')
PWSH = shutil.which('pwsh') or ('/opt/pwsh/pwsh' if os.path.exists('/opt/pwsh/pwsh') else None)


def w(f, t):
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, 'w', encoding='utf-8') as g: g.write(t)


def commande():
    t = open(LANCEUR, encoding='ascii').read()
    return re.search(r'-Command "(.*)"\r?\n', t).group(1)


@unittest.skipUnless(PWSH, 'PowerShell (pwsh) absent')
class Recherche(unittest.TestCase):
    def arbre(self, installe=True, versions=('3', '10')):
        rev = dossier_essai('lancer_worker_lmstudio_v4')
        src = os.path.join(rev, '00_competences_claude', 'outils')
        w(os.path.join(src, 'worker_lmstudio', 'worker_lmstudio_v3.ps1'), 'Write-Output "LANCE:source"; exit 0\n')
        if installe:
            F = os.path.join(rev, '00_espace_cloud_claude', 'file_lmstudio'); os.makedirs(os.path.join(F, 'entree'))
            for v in versions: w(os.path.join(F, 'outil', f'worker_lmstudio_v{v}.ps1'), f'Write-Output "LANCE:installe-v{v}"; exit 0\n')
        return rev

    def lancer(self, dossier):
        c = commande().replace('%~dp0', dossier.rstrip('/') + '/')
        return subprocess.run([PWSH, '-NoProfile', '-Command', c], capture_output=True, text=True, timeout=120)

    def test_depuis_outils(self):
        rev = self.arbre(); r = self.lancer(os.path.join(rev, '00_competences_claude', 'outils', 'lancer_worker_lmstudio'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn('LANCE:installe-v10', r.stdout); self.assertNotIn('source', r.stdout)

    def test_depuis_installation(self):
        rev = self.arbre(versions=('3',)); r = self.lancer(os.path.join(rev, '00_espace_cloud_claude', 'file_lmstudio', 'outil'))
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn('LANCE:installe-v3', r.stdout)

    def test_sans_installation(self):
        rev = self.arbre(installe=False); r = self.lancer(os.path.join(rev, '00_competences_claude', 'outils', 'lancer_worker_lmstudio'))
        self.assertEqual(r.returncode, 5); self.assertIn('introuvable', r.stdout); self.assertNotIn('LANCE', r.stdout)


class Fichier(unittest.TestCase):
    def test_forme(self):
        b = open(LANCEUR, 'rb').read(); t = b.decode('ascii')
        self.assertNotIn(b'\n', b.replace(b'\r\n', b''))
        for k in ('rem OUTIL: lancer_worker_lmstudio', 'rem VERSION: 4', 'rem BANC: tests/test_lancer_worker_lmstudio_v4.py', 'pause', '%~dp0'):
            self.assertIn(k, t)
        code = '\n'.join(l for l in t.splitlines() if not l.lower().startswith('rem '))
        self.assertNotRegex(code, r'worker_lmstudio_v\d+\.ps1')                 # aucune version d'ouvrier écrite en dur (hors commentaires)
        self.assertIn("worker_lmstudio_v*.ps1", t)


if __name__ == '__main__':
    unittest.main()
