"""Cas fixes du banc de evaluer_travail (v1) : chaque cas construit un dossier de travail et donne les constats attendus
(règle, chemin). Le banc exécute l'outil avec --sans-xsd --sans-manifeste --json."""
import os, json, hashlib, stat


def _ecrire(base, rel, texte, ro=False):
    ch = os.path.join(base, rel); os.makedirs(os.path.dirname(ch), exist_ok=True)
    with open(ch, 'w', encoding='utf-8') as f: f.write(texte)
    if ro: os.chmod(ch, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return ch


def _sha(t): return hashlib.sha256(t.encode('utf-8')).hexdigest()


def _conforme(base, nom='11_essai_conforme'):
    d = os.path.join(base, nom)
    _ecrire(d, 'LISEZMOI_v1.md', '# Essai\n')
    _ecrire(d, 'TRAVAIL_v1.json', json.dumps(dict(sujet='essai', source='00_sources/doc_v1.txt', auteur_revisions='Reevaluation - Claude',
                                                  version_cible='2.0.0', couverture=None, auteurs_relecteurs=[])))
    _ecrire(d, '00_sources/doc_v1.txt', 'source\n', ro=True)
    _ecrire(d, '00_sources/sha256_sources_v1.txt', f'{_sha("source" + chr(10))}  00_sources/doc_v1.txt\n', ro=True)
    _ecrire(d, '01_analyse/notes_v1.md', 'notes\n')
    _ecrire(d, '90_scripts/outil_v1.py', 'print(1)\n')
    _ecrire(d, '95_journal/audit_v1.md', 'audit\n')
    _ecrire(d, '98_livrables/Rapport_v2.0.0.md', 'final\n', ro=True)
    _ecrire(d, '98_livrables/empreintes_livrables_v2.0.0.txt', f'{_sha("final" + chr(10))[:16]} Rapport_v2.0.0.md\n')
    _ecrire(d, '99_livrables_modifiables/Rapport_v2.0.0.md', 'final\n')
    return d


def _violations(base):
    d = os.path.join(base, '1_essai_violations')
    _ecrire(d, 'notes.txt', 'x')
    _ecrire(d, 'scripts/x.py', 'x')
    _ecrire(d, '00_sources/doc_v1.txt', 'source modifiée\n')
    _ecrire(d, '00_sources/autre.txt', 'autre\n')
    _ecrire(d, '00_sources/sha256_sources_v1.txt', f'{_sha("source" + chr(10))}  00_sources/doc_v1.txt\n')
    _ecrire(d, '01_etape/résumé_v1.md', 'r')
    _ecrire(d, '01_etape/plan_v2.md', 'plan A')
    _ecrire(d, '02_suite/plan_v2.md', 'plan B')
    _ecrire(d, '02_suite/Rapport_v6.0.1.pdf', '%PDF-1.4 x')
    _ecrire(d, '95_journal/audit_v1.md', 'a')
    _ecrire(d, '98_livrables/Rapport_v8.0.1.md', 'final')
    return d


def _ecrasement(base):
    d = _conforme(base, '12_essai_ecrasement')
    _ecrire(d, '01_etape/a_v1.md', 'nouveau contenu')
    _ecrire(d, '01_etape/c_v1.md', 'début + ajout')
    h = lambda t: hashlib.sha256(t.encode()).hexdigest()[:16]
    man = {'01_etape/a_v1.md': [h('ancien contenu'), len('ancien contenu')],
           '01_etape/b_v1.md': [h('b'), 1],
           '01_etape/c_v1.md': [h('début'), len('début'.encode())]}
    _ecrire(d, '95_journal/manifestes/manifeste_20261015_000000.json', json.dumps(dict(date='2026-10-15T00:00:00Z', fichiers=man)))
    return d


def _cmd(tool, d, j): return [tool, d, '--sans-xsd', '--sans-manifeste', '--json', j]


CAS = [
    dict(nom='cas01_conforme', construire=_conforme, commande=_cmd, attendu=[]),
    dict(nom='cas02_violations', construire=_violations, commande=_cmd, attendu=[
        ('O1', '1_essai_violations'), ('O2', '99_livrables_modifiables'), ('O3', 'scripts'), ('O4', 'notes.txt'),
        ('O5', 'TRAVAIL_vN.json'), ('O6', 'LISEZMOI_vN.md'),
        ('E1', '00_sources/doc_v1.txt'), ('E2', '00_sources/doc_v1.txt'), ('E1', '00_sources/autre.txt'), ('E2', '00_sources/autre.txt'),
        ('E3', '98_livrables'), ('E3', '98_livrables/Rapport_v8.0.1.md'), ('E4', '98_livrables/Rapport_v8.0.1.md'),
        ('N1', 'notes.txt'), ('N1', 'scripts/x.py'), ('N2', '01_etape/résumé_v1.md'), ('N3', '98_livrables/Rapport_v8.0.1.md'),
        ('N4', '02_suite/Rapport_v6.0.1.pdf'), ('N5', 'plan_v2.md')]),
    dict(nom='cas03_ecrasement', construire=_ecrasement, commande=_cmd, attendu=[
        ('E5', '01_etape/a_v1.md'), ('E5', '01_etape/b_v1.md')]),
]
