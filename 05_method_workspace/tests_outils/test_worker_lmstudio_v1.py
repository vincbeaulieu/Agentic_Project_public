"""Tests statiques de l'ouvrier PowerShell (pas de PowerShell dans le cloud) : syntaxe équilibrée, fonctions présentes,
aucune suppression de fichier, seules adresses locales, arrêts prévus (API, LM Studio interrompu, file vide, fichier ARRET)."""
import re, unittest
from aide_tests_v1 import chemin_outil
T = open(chemin_outil('worker_lmstudio', ext='ps1'), encoding='utf-8').read()
CODE = re.sub(r"(?s)@'.*?'@", "''", re.sub(r'(?m)^\s*#.*$', '', T))           # sans commentaires ni page HTML


class Statique(unittest.TestCase):
    def test_equilibre(self):
        sans_chaines = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"", '""', CODE)
        for a, b in ('{}', '()', '[]'): self.assertEqual(sans_chaines.count(a), sans_chaines.count(b), a + b)

    def test_fonctions(self):
        for f in ('Servir-Controle', 'Appeler', 'Choisir', 'Charger-Lot', 'Clore-Lot', 'Ecrire-Etat', 'Attendre'):
            self.assertRegex(CODE, r'function ' + f + r'\b')

    def test_jamais_de_suppression(self):
        self.assertNotRegex(CODE, r'(?i)\b(Remove-Item|del |rm |rmdir|Clear-Content)\b')

    def test_adresses_locales_seulement(self):
        for u in re.findall(r'https?://[^\s\'"]+', T): self.assertRegex(u, r'^http://(127\.0\.0\.1|localhost)[:/]', u)

    def test_arrets_prevus(self):
        for motif in ("'/arreter'", 'arret_si_lmstudio_absent_min', 'arret_si_inactif_min', "'ARRET'", '$cts.Cancel()', 'IPAddress]::Loopback'):
            self.assertIn(motif, T)


if __name__ == '__main__':
    unittest.main()
