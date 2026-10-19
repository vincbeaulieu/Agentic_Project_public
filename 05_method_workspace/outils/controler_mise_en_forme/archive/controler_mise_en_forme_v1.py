"""
OUTIL: controler_mise_en_forme
VERSION: 1
RESUME: Contrôle déterministe de la mise en forme d'un rapport Word révisé en suivi, avec la provenance de chaque écart (auteur de la révision qui l'a introduit, ou « base » pour le texte accepté). Écarts : MF1 passage sans taille explicite dont la taille effective (style, valeurs par défaut du document) diffère de la taille dominante de son paragraphe ; MF2 taille explicite différente de la taille dominante du paragraphe ; MF3 résidu de Markdown (*…*, **…**, « * » en tête, #, `) ; MF4 paragraphe entièrement supprimé en suivi dont la marque de paragraphe est gardée (ligne vide après acceptation) ; MF5 paragraphe vide hors des cas utiles (entre deux tableaux, porteur d'un saut de page, d'une section ou d'un signet) ; MF6 police directe hors de la police du document et des polices permises (équations). La page de garde (tout ce qui précède la table des matières) n'est jamais contrôlée pour correction. Commande « comparer » : écarts nouveaux d'une version à l'autre, par auteur, avec code 1 si l'auteur visé en a introduit (contrôle après chaque passe).
USAGE: python3 outils/controler_mise_en_forme.py releve <docx> [--json <sortie.json>]  |  comparer <avant.docx> <apres.docx> [--auteur "Reevaluation - Claude"] [--json <sortie.json>]
ENTREES: docx (word/document.xml, word/styles.xml)
SORTIES: résumé à l'écran ; JSON facultatif {profil, ecarts:[{code, index, zone, auteur, texte, detail}], compte} ; événement dans journal/ ; code 1 si « comparer » trouve des écarts nouveaux de l'auteur visé
CATEGORIE: revision_rapport
BANC: tests/test_controler_mise_en_forme_v1.py
REMPLACE: -
"""
import sys, os, re, json, zipfile, collections
H = os.path.dirname(os.path.abspath(__file__)); O = H
while os.path.basename(O) != 'outils' and os.path.dirname(O) != O: O = os.path.dirname(O)
for p in (os.path.join(O, '_compat'), O):
    if p not in sys.path: sys.path.insert(0, p)
from lxml import etree                                       # noqa: E402
from cc_lib_v4 import evenement                              # noqa: E402

VERSION = 1; OUTIL = 'controler_mise_en_forme'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
POLICES_PERMISES = {'Cambria Math'}
# Résidus de Markdown : emphase appariée (*mot*, **mot**, « * mot* »), titre « # », code « ` ». Une étoile d'appel de note (« * A : … », « B* ») n'en est pas un.
MD = re.compile(r'(?:^|[\s(])\*{1,2}\s?[^\s*][^*\n]{0,80}?\*{1,2}(?=\s*[,.;:)]|\s|$)|^\s*#{1,6}\s|`[^`]+`')
CODES = {'MF1': 'passage sans taille explicite, plus grand ou plus petit que son paragraphe', 'MF2': 'taille explicite différente de celle du paragraphe',
         'MF3': 'résidu de Markdown', 'MF4': 'paragraphe supprimé en suivi dont la marque reste (ligne vide après acceptation)',
         'MF5': 'paragraphe vide inutile', 'MF6': 'police directe hors police du document'}


def ln(e): return e.tag.split('}')[1] if isinstance(e.tag, str) else ''


def dans(e, *noms):
    return any(ln(a) in noms for a in e.iterancestors())


def auteur(e):
    """Auteur de l'insertion (ou du déplacement) qui contient e, sinon « base »."""
    for a in e.iterancestors():
        if ln(a) in ('ins', 'moveTo'): return a.get(W + 'author')
        if ln(a) == 'p': break
    return 'base'


class Styles:
    def __init__(self, z):
        s = etree.fromstring(z.read('word/styles.xml')); self.taille, self.base, self.police = {}, {}, {}
        dd = s.find(f'{W}docDefaults/{W}rPrDefault/{W}rPr')
        self.defaut_taille = (dd.find(W + 'sz').get(W + 'val') if dd is not None and dd.find(W + 'sz') is not None else '20')
        f = dd.find(W + 'rFonts') if dd is not None else None
        self.defaut_police = (f.get(W + 'ascii') or f.get(W + 'hAnsi')) if f is not None else None
        for st in s.iter(W + 'style'):
            i = st.get(W + 'styleId'); b = st.find(W + 'basedOn'); self.base[i] = b.get(W + 'val') if b is not None else None
            sz = st.find(f'{W}rPr/{W}sz'); self.taille[i] = sz.get(W + 'val') if sz is not None else None

    def taille_style(self, i, n=0):
        if i is None or n > 12: return self.defaut_taille
        return self.taille.get(i) or self.taille_style(self.base.get(i), n + 1)


def texte_visible(e):
    return ''.join(t.text or '' for t in e.iter(W + 't') if not dans(t, 'del', 'moveFrom'))


def zone(p, st):
    if dans(p, 'tc'): return 'tableau'
    if st.startswith('TOC'): return 'sommaire'
    if st.startswith('Heading') or st in ('Title', 'Subtitle'): return 'titres'
    if st == 'ListParagraph': return 'liste'
    return 'corps'


def pstyle(p):
    s = p.find(f'{W}pPr/{W}pStyle'); return s.get(W + 'val') if s is not None else 'Normal'


def runs_texte(p):
    """Passages visibles porteurs de texte (hors supprimés, hors champs, exposants et indices)."""
    for r in p.iter(W + 'r'):
        if dans(r, 'del', 'moveFrom') or r.getparent() is None: continue
        t = ''.join(x.text or '' for x in r.findall(W + 't'))
        if not t.strip(): continue
        rp = r.find(W + 'rPr')
        if rp is not None and rp.find(W + 'vertAlign') is not None: continue
        yield r, t


def taille_run(r, st, S):
    rp = r.find(W + 'rPr'); sz = rp.find(W + 'sz') if rp is not None else None
    if sz is not None: return sz.get(W + 'val'), True
    rs = rp.find(W + 'rStyle') if rp is not None else None
    return (S.taille_style(rs.get(W + 'val')) if rs is not None else S.taille_style(st)), False


def dominante(p, st, S):
    """Taille dominante (en caractères) des passages « base » à taille explicite du paragraphe ; à défaut, de tous ses passages explicites."""
    for filtre in (lambda r: auteur(r) == 'base', lambda r: True):
        c = collections.Counter()
        for r, t in runs_texte(p):
            v, expl = taille_run(r, st, S)
            if expl and filtre(r): c[v] += len(t)
        if c: return c.most_common(1)[0][0]
    return None


def debut_sommaire(paras):
    for i, p in enumerate(paras):
        if pstyle(p).startswith('TOC') or texte_visible(p).strip().lower() in ('table des matières', 'sommaire'): return i
    return 0


def profil_tailles(paras, lim, S):
    """Taille dominante des passages « base » à taille explicite, par zone (corps, liste) : référence d'un paragraphe sans taille explicite."""
    c = collections.defaultdict(collections.Counter)
    for p in paras[lim:]:
        st = pstyle(p); zn = zone(p, st)
        if zn not in ('corps', 'liste'): continue
        for r, t in runs_texte(p):
            v, expl = taille_run(r, st, S)
            if expl and auteur(r) == 'base': c[zn][v] += len(t)
    return {zn: c[zn].most_common(1)[0][0] for zn in c}


def releve(chemin, couverture=None):
    z = zipfile.ZipFile(chemin); return releve_arbre(etree.fromstring(z.read('word/document.xml')), z, os.path.basename(chemin), couverture)


def releve_arbre(doc, z, nom='document', couverture=None):
    S = Styles(z)
    body = doc.find(W + 'body'); paras = [p for p in body.iter(W + 'p')]
    lim = debut_sommaire(paras) if couverture is None else couverture
    PT = profil_tailles(paras, lim, S)
    E = []; enfants = list(body)
    def ecart(code, i, zn, aut, p, detail=''): E.append(dict(code=code, index=i, zone=zn, auteur=aut, texte=texte_visible(p)[:90], detail=detail))
    voisins = {}
    for k, e in enumerate(enfants):
        if ln(e) == 'p': voisins[id(e)] = (ln(enfants[k - 1]) if k else '', ln(enfants[k + 1]) if k + 1 < len(enfants) else '')
    for i, p in enumerate(paras):
        st = pstyle(p); zn = zone(p, st)
        if i < lim or zn == 'sommaire': continue
        vis = texte_visible(p); sup = ''.join(t.text or '' for t in p.iter(W + 'delText'))
        marque_sup = p.find(f'{W}pPr/{W}rPr/{W}del') is not None
        if not vis.strip() and not p.findall('.//' + W + 'drawing') and not p.findall('.//' + W + 'object'):
            dernier_cellule = dans(p, 'tc') and p.getnext() is None and ln(p.getparent()) == 'tc'
            if sup.strip() and not marque_sup and not dernier_cellule:
                auts = collections.Counter(a.get(W + 'author') for a in p.iter(W + 'del') if ln(a.getparent()) != 'rPr')
                ecart('MF4', i, zn, auts.most_common(1)[0][0] if auts else 'base', p, sup[:60])
            elif not sup.strip() and not marque_sup and zn in ('corps', 'liste'):
                utile = (p.find(f'{W}pPr/{W}sectPr') is not None or any(b.get(W + 'type') == 'page' for b in p.iter(W + 'br'))
                         or p.find(f'{W}pPr/{W}pageBreakBefore') is not None or p.findall('.//' + W + 'bookmarkStart')
                         or voisins.get(id(p), ('', ''))[0] == 'tbl' and voisins.get(id(p), ('', ''))[1] == 'tbl' or dans(p, 'tc'))
                if not utile:
                    m = p.find(f'{W}pPr/{W}rPr/{W}ins'); ecart('MF5', i, zn, m.get(W + 'author') if m is not None else 'base', p)
            continue
        if zn in ('corps', 'liste', 'titres') and MD.search(vis):
            a = collections.Counter(auteur(t) for t in p.iter(W + 't') if not dans(t, 'del') and re.search(r'[*#`]', t.text or ''))
            ecart('MF3', i, zn, a.most_common(1)[0][0] if a else 'base', p, MD.search(vis).group(0).strip()[:40])
        if zn in ('corps', 'liste'):
            dom = dominante(p, st, S) or PT.get(zn)
            for r, t in runs_texte(p):
                v, expl = taille_run(r, st, S)
                if dom and v != dom: ecart('MF1' if not expl else 'MF2', i, zn, auteur(r), p, f'{int(v) / 2:g} pt au lieu de {int(dom) / 2:g} pt : « {t.strip()[:30]} »')
        for r, t in runs_texte(p):
            f = r.find(f'{W}rPr/{W}rFonts')
            if f is not None:
                nom = f.get(W + 'ascii') or f.get(W + 'hAnsi')
                if nom and nom not in POLICES_PERMISES and nom != S.defaut_police: ecart('MF6', i, zn, auteur(r), p, nom)
    profil = dict(taille_corps=PT.get('corps'), taille_liste=PT.get('liste'), police_document=S.defaut_police, taille_defaut=S.defaut_taille, debut_sommaire=lim)
    compte = collections.Counter((e['code'], e['auteur']) for e in E)
    return dict(fichier=nom, profil=profil, ecarts=E, compte={f'{c} / {a}': n for (c, a), n in sorted(compte.items())})


def cle(e): return (e['code'], e['auteur'], e['texte'], e['detail'])


def comparer(avant, apres, auteur_vise=None):
    A, B = releve(avant), releve(apres)
    vus = collections.Counter(cle(e) for e in A['ecarts']); nouveaux = []
    for e in B['ecarts']:
        k = cle(e)
        if vus[k]: vus[k] -= 1
        else: nouveaux.append(e)
    vises = [e for e in nouveaux if auteur_vise is None or e['auteur'] == auteur_vise]
    return dict(avant=A['fichier'], apres=B['fichier'], nouveaux=nouveaux, vises=vises, auteur=auteur_vise)


def opt(a, k, d=None): return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


USAGE = __doc__.split('USAGE:')[1].split('ENTREES:')[0].strip()


def main(a=None):
    a = sys.argv[1:] if a is None else a
    if not a or a[0] not in ('releve', 'comparer'): print(USAGE); return 2
    js = opt(a, '--json')
    if a[0] == 'releve':
        R = releve(a[1]); print(f"{R['fichier']} : {len(R['ecarts'])} écart(s) ; profil {R['profil']}")
        for k, n in R['compte'].items(): print(f'  {k} : {n}')
        evenement(OUTIL, VERSION, 'releve', dict(ecarts=len(R['ecarts']), codes=sorted({e['code'] for e in R['ecarts']})))
        code = 0
    else:
        R = comparer(a[1], a[2], opt(a, '--auteur'))
        print(f"{len(R['nouveaux'])} écart(s) nouveau(x) de {R['avant']} à {R['apres']}" + (f" ; {len(R['vises'])} de « {R['auteur']} »" if R['auteur'] else ''))
        for e in R['vises'][:30]: print(f"  {e['code']} ¶{e['index']} {e['auteur']} : {e['detail'] or e['texte'][:60]}")
        evenement(OUTIL, VERSION, 'comparer', dict(nouveaux=len(R['nouveaux']), vises=len(R['vises']), verdict='conforme' if not R['vises'] else 'non conforme'))
        code = 1 if (R['auteur'] and R['vises']) else 0
    if js:
        with open(js, 'w', encoding='utf-8') as g: json.dump(R, g, ensure_ascii=False, indent=1)
    return code


if __name__ == '__main__':
    sys.exit(main())
