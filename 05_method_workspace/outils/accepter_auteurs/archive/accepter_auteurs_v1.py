"""
OUTIL: accepter_auteurs
VERSION: 1
RESUME: Docx en suivi des modifications : accepte les révisions d'un ou plusieurs auteurs désignés, comme « Révision > Accepter » de Word limité à ces auteurs, et laisse intactes celles des autres auteurs. Insertions gardées (conteneur retiré) ; suppressions retirées avec leur contenu (marqueurs de commentaire et signets sortis et gardés) ; marque de paragraphe insérée validée ; marque de paragraphe supprimée : le paragraphe se fond dans le suivant, qui garde ses propriétés (comme Word) ; rangée supprimée retirée (tableau retiré s'il n'a plus de rangée) ; modifications de mise en forme suivies (rPrChange, pPrChange, tblPrChange, tcPrChange, trPrChange, sectPrChange, tblGridChange) validées ; déplacements suivis acceptés. Toutes les parties qui portent du texte (corps, notes, en-têtes, pieds de page, commentaires). Images et relations rendues orphelines par l'acceptation retirées du paquet. Refuse de toucher à un champ coupé par une suppression ; une marque supprimée qui ne peut pas se fondre (section, fin de conteneur, avant un tableau) est listée.
USAGE: python3 accepter_auteurs_v1.py <entree.docx> <sortie.docx> --auteurs "Auteur A;Auteur B" [--json <bilan.json>]
ENTREES: docx en suivi des modifications
SORTIES: <sortie.docx> (nouveau fichier, jamais écrasé : code 3 s'il existe) ; bilan par partie et par type ; code 0, 1 si des cas sont laissés en place (listés), 2 usage
CATEGORIE: docx
BANC: tests/test_accepter_auteurs_v1.py
REMPLACE: -
"""
import sys, os, re, json, zipfile, collections, posixpath
from lxml import etree

VERSION = 1; OUTIL = 'accepter_auteurs'
WN = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
RELNS = 'http://schemas.openxmlformats.org/package/2006/relationships'
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
def q(t, ns=WN): return '{%s}%s' % (ns, t)
def ln(e): return etree.QName(e).localname if isinstance(e.tag, str) else None
KEEP = ('commentRangeStart', 'commentRangeEnd', 'bookmarkStart', 'bookmarkEnd', 'permStart', 'permEnd')
CHANGES = ('rPrChange', 'pPrChange', 'tblPrChange', 'tcPrChange', 'trPrChange', 'sectPrChange', 'tblGridChange', 'tblPrExChange', 'numberingChange')
PARTIES = re.compile(r'^word/(document|footnotes|endnotes|comments|header\d*|footer\d*)\.xml$')
NON_BLOC = ('bookmarkStart', 'bookmarkEnd', 'commentRangeStart', 'commentRangeEnd', 'proofErr', 'permStart', 'permEnd')


def deplier(e):
    par = e.getparent(); idx = par.index(e)
    for ch in list(e): par.insert(idx, ch); idx += 1
    par.remove(e)


def sortir_marqueurs(e):
    """Retire de e les marqueurs à garder (commentaires, signets) et les runs de référence de commentaire, placés avant e."""
    for x in [x for x in e.iter() if ln(x) in KEEP]:
        x.getparent().remove(x); e.addprevious(x)
    for r in [r for r in e.iter(q('r')) if r.find(q('commentReference')) is not None]:
        r.getparent().remove(r); e.addprevious(r)


def sortir_de_rangee(tr, tbl):
    """Avant de retirer une rangée : ses marqueurs de commentaire et signets passent devant le tableau ; une référence de commentaire
    va à la fin du paragraphe qui précède le tableau (sinon au début du suivant) : le commentaire garde un ancrage."""
    for x in [x for x in tr.iter() if ln(x) in KEEP]:
        x.getparent().remove(x); tbl.addprevious(x)
    refs = [r for r in tr.iter(q('r')) if r.find(q('commentReference')) is not None]
    if not refs: return
    p = tbl.getprevious()
    while p is not None and ln(p) != 'p': p = p.getprevious()
    for r in refs:
        r.getparent().remove(r)
        if p is not None: p.append(r)
        else:
            s = tbl.getnext()
            while s is not None and ln(s) != 'p': s = s.getnext()
            ppr = s.find(q('pPr')) if s is not None else None
            (ppr.addnext(r) if ppr is not None else s.insert(0, r)) if s is not None else tbl.addprevious(r)


def champ_coupe(e):
    """Vrai si e contient un champ incomplet (fldChar begin/end non apparié) : le retirer casserait le champ."""
    s = 0
    for f in e.iter(q('fldChar')):
        t = f.get(q('fldCharType'))
        s += 1 if t == 'begin' else -1 if t == 'end' else 0
    return s != 0


def visible(p):
    """Contenu qui resterait d'un paragraphe : texte hors suppression, dessins, objets."""
    for x in p.iter(q('t'), q('drawing'), q('pict'), q('object'), q('tab'), q('br'), q('sym')):
        if not any(ln(a) in ('del', 'moveFrom') for a in x.iterancestors()): return True
    return False


def bloc_suivant(p):
    s = p.getnext()
    while s is not None and ln(s) in NON_BLOC: s = s.getnext()
    return s


def accepter(root, auteurs, laisses=None):
    """Accepte dans l'arbre root les révisions des auteurs donnés ; retourne le bilan ; laisses reçoit les cas non traités."""
    A = set(auteurs); n = collections.Counter(); laisses = laisses if laisses is not None else []
    de = lambda e: e.get(q('author')) in A
    # 1. rangées
    for tr in list(root.iter(q('tr'))):
        trpr = tr.find(q('trPr'))
        if trpr is None: continue
        if any(de(m) for m in trpr.findall(q('del'))):
            tbl = tr.getparent()
            if champ_coupe(tr): laisses.append(('champ_coupe', 'tr')); continue
            sortir_de_rangee(tr, tbl)
            tbl.remove(tr); n['rangee_supprimee'] += 1
            if tbl.find(q('tr')) is None:
                for x in [x for x in tbl if ln(x) in KEEP]: tbl.remove(x); tbl.addprevious(x)
                tbl.getparent().remove(tbl); n['tableau_retire'] += 1
            continue
        for m in trpr.findall(q('ins')):
            if de(m): trpr.remove(m); n['rangee_inseree'] += 1
    # 2. mise en forme suivie
    for t in CHANGES:
        for ch in list(root.iter(q(t))):
            if de(ch): ch.getparent().remove(ch); n[t] += 1
    # 3. contenu : déplacements, insertions, suppressions
    for t in ('moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd'):
        for e in list(root.iter(q(t))):
            if de(e): e.getparent().remove(e)
    for e in list(root.iter(q('ins'), q('moveTo'))):
        if ln(e.getparent()) in ('rPr', 'trPr', 'tcPr') or not de(e): continue
        deplier(e); n[ln(e)] += 1
    for e in list(root.iter(q('del'), q('moveFrom'))):
        if ln(e.getparent()) in ('rPr', 'trPr', 'tcPr') or not de(e): continue
        if e.getparent() is None: continue
        if champ_coupe(e): laisses.append(('champ_coupe', ln(e))); continue
        sortir_marqueurs(e); e.getparent().remove(e); n[ln(e)] += 1
    # 4. marques de paragraphe (ordre inverse : une chaîne de marques supprimées se fond de proche en proche)
    for p in reversed(list(root.iter(q('p')))):
        ppr = p.find(q('pPr')); rp = ppr.find(q('rPr')) if ppr is not None else None
        if rp is None: continue
        for m in list(rp):
            if ln(m) == 'ins' and de(m): rp.remove(m); n['marque_inseree'] += 1
        mk = [m for m in rp if ln(m) == 'del' and de(m)]
        if not mk: continue
        s = bloc_suivant(p)
        if ppr.find(q('sectPr')) is not None:
            laisses.append(('marque_section', p.get('{http://schemas.microsoft.com/office/word/2010/wordml}paraId'))); continue
        if s is not None and ln(s) == 'p':
            for m in mk: rp.remove(m)
            sppr = s.find(q('pPr')); k = 0 if sppr is None else s.index(sppr) + 1
            for x in [x for x in p if x is not ppr]:
                s.insert(k, x); k += 1
            p.getparent().remove(p); n['marque_supprimee'] += 1
        elif not visible(p):
            prev = p.getprevious()
            for x in [x for x in p.iter() if ln(x) in KEEP]:
                x.getparent().remove(x)
                (prev.append(x) if prev is not None and ln(prev) == 'p' else p.addprevious(x))
            p.getparent().remove(p); n['paragraphe_vide_retire'] += 1
        else:
            laisses.append(('marque_non_fusionnable', p.get('{http://schemas.microsoft.com/office/word/2010/wordml}paraId')))
    return dict(n)


def auteurs_revisions(root):
    c = collections.Counter()
    for t in ('ins', 'del', 'moveFrom', 'moveTo') + CHANGES:
        for e in root.iter(q(t)): c[(t, e.get(q('author')))] += 1
    return c


def nettoyer_relations(fichiers):
    """Retire les relations d'image que plus aucune partie n'emploie, puis les médias que plus aucune relation ne vise."""
    retires = []
    for nom in [k for k in fichiers if k.startswith('word/_rels/') and k.endswith('.rels')]:
        partie = 'word/' + nom[len('word/_rels/'):-len('.rels')]
        if partie not in fichiers: continue
        xml = fichiers[partie].decode('utf-8', 'ignore')
        rels = etree.fromstring(fichiers[nom]); chg = False
        for r in list(rels):
            if r.get('Type', '').endswith('/image') and r.get('TargetMode') != 'External':
                if not re.search(r'"%s"' % re.escape(r.get('Id')), xml):
                    rels.remove(r); chg = True; retires.append((partie, r.get('Id'), r.get('Target')))
        if chg: fichiers[nom] = etree.tostring(rels, xml_declaration=True, encoding='UTF-8', standalone=True)
    vises = set()
    for nom, b in fichiers.items():
        if nom.endswith('.rels'):
            base = posixpath.dirname(posixpath.dirname(nom))
            for r in etree.fromstring(b):
                if r.get('TargetMode') != 'External':
                    vises.add(posixpath.normpath(posixpath.join(base, r.get('Target'))).lstrip('/'))
    medias = [k for k in fichiers if k.startswith('word/media/') and k not in vises]
    for k in medias: del fichiers[k]
    return retires, medias


def traiter(entree, sortie, auteurs):
    if os.path.exists(sortie): raise FileExistsError(sortie)
    zin = zipfile.ZipFile(entree); infos = zin.infolist(); fichiers = {i.filename: zin.read(i.filename) for i in infos}
    bilan, laisses = {}, []
    for nom in list(fichiers):
        if not PARTIES.match(nom): continue
        root = etree.fromstring(fichiers[nom]); L = []
        b = accepter(root, auteurs, L)
        if b or L:
            fichiers[nom] = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            bilan[nom] = b; laisses += [(nom,) + x for x in L]
    rel, med = nettoyer_relations(fichiers)
    with zipfile.ZipFile(sortie, 'x', zipfile.ZIP_DEFLATED) as zo:
        for i in infos:
            if i.filename in fichiers: zo.writestr(i, fichiers[i.filename])
    return dict(bilan=bilan, laisses=laisses, relations_retirees=rel, medias_retires=med)


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if len(a) < 4 or '--auteurs' not in a: print('USAGE: ' + __doc__.split('USAGE: ')[1].split('\n')[0]); return 2
    entree, sortie = a[0], a[1]; auteurs = [x.strip() for x in a[a.index('--auteurs') + 1].split(';') if x.strip()]
    if os.path.exists(sortie): print(f'existe déjà, jamais écrasé : {sortie}'); return 3
    R = traiter(entree, sortie, auteurs)
    tot = collections.Counter()
    for b in R['bilan'].values(): tot.update(b)
    print(f'accepté ({", ".join(auteurs)}) : ' + ', '.join(f'{k} {v}' for k, v in sorted(tot.items())))
    print(f'relations d\'image retirées : {len(R["relations_retirees"])} ; médias retirés : {len(R["medias_retires"])}')
    for x in R['laisses']: print('  LAISSÉ', x)
    if '--json' in a:
        with open(a[a.index('--json') + 1], 'x', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '_compat'))
        from cc_lib_v4 import evenement
        evenement(OUTIL, VERSION, 'acceptation', dict(auteurs=len(auteurs), revisions=sum(tot.values()), laisses=len(R['laisses'])))
    except Exception: pass
    return 1 if R['laisses'] else 0


if __name__ == '__main__':
    sys.exit(main())
