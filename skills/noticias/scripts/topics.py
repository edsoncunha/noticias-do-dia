"""Agrupa as manchetes por assunto e separa, no texto das matérias, o que é comum do que é exclusivo.

Tudo aqui é determinístico e local: o objetivo é que o modelo leia assuntos já agrupados e só
o trecho novo de cada veículo, em vez do índice inteiro e de textos que se repetem.
"""

import math
import re
import unicodedata
from collections import Counter, defaultdict

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para pra com sem
sobre entre até após ante contra desde e ou mas que se não sim mais menos muito muita já ainda também
como quando onde quem qual quais seu sua seus suas ele ela eles elas isso isto esse essa este esta
ser estar ter haver foi era são está estão tem têm vai vão diz dizem afirma após anos ano dia dias
hoje ontem amanhã novo nova novos novas sobre veja entenda saiba após durante pode podem deve devem
brasil brasileiro brasileira governo presidente diz após mil milhões bilhões r$ us$ contra sobre
nesta neste nessa nesse terça quarta quinta sexta sábado domingo segunda feira vídeo vídeos ao aos à às
the of and to in for on is
""".split())


def norm(word):
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


def stem(tok):
    """Radical grosseiro para juntar singular e plural (eleição/eleições, vitória/vitórias)."""
    for suf, rep in (("coes", "cao"), ("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el")):
        if tok.endswith(suf) and len(tok) > len(suf) + 2:
            tok = tok[: -len(suf)] + rep
            break
    else:
        if tok.endswith("s") and len(tok) > 4:
            tok = tok[:-1]
    return tok[:8]


def tokens(text):
    out = []
    for w in re.findall(r"[\wÀ-ÿ\-]+", text):
        n = norm(w)
        if len(n) >= 3 and n not in STOPWORDS and not n.isdigit():
            out.append(stem(n))
    return out


def _vectors(items):
    """TF-IDF com o título pesando o dobro do resumo do feed."""
    tfs = []
    for it in items:
        tf = Counter()
        for t in tokens(it["title"]):
            tf[t] += 2
        for t in tokens(it.get("summary", "")[:300]):
            tf[t] += 1
        tfs.append(tf)
    df = Counter(t for tf in tfs for t in tf)
    n = len(items)
    vecs = []
    for tf in tfs:
        v = {t: c * math.log(n / df[t]) for t, c in tf.items() if df[t] > 1}
        norm_ = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm_ for t, x in v.items()})
    return vecs


def _cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def cluster(items, threshold=0.33, merge_threshold=0.38):
    """Agrupamento em estrela: a manchete com mais vizinhas vira centro e leva as parecidas com ela.

    Diferente de componentes conexos, não encadeia assuntos distintos que só compartilham um nome
    ("Lula parabeniza..." e "Lula sanciona..."). Devolve listas de índices de `items`.
    """
    vecs = _vectors(items)
    index = defaultdict(list)
    for i, v in enumerate(vecs):
        for t in v:
            index[t].append(i)
    neigh = defaultdict(dict)
    for i, v in enumerate(vecs):
        cands = {j for t in v for j in index[t] if j > i}
        for j in cands:
            s = _cos(v, vecs[j])
            if s >= threshold:
                neigh[i][j] = neigh[j][i] = s

    def weight(i):  # vizinhas de veículos diferentes contam mais que as do mesmo veículo
        return len({items[j]["source"] for j in neigh[i]}), len(neigh[i])

    assigned, groups = set(), []
    for i in sorted(range(len(items)), key=weight, reverse=True):
        if i in assigned:
            continue
        members = [i] + [j for j in neigh[i] if j not in assigned]
        assigned.update(members)
        groups.append(members)

    # Segunda passada: manchetes isoladas que se parecem com o conjunto de um grupo (centróide).
    singles = [g[0] for g in groups if len(g) == 1]
    multi = [g for g in groups if len(g) > 1]
    centroids = []
    for g in multi:
        c = defaultdict(float)
        for j in g:
            for t, x in vecs[j].items():
                c[t] += x / len(g)
        centroids.append(c)
    rest = []
    for i in singles:
        best, score = None, threshold
        for k, c in enumerate(centroids):
            s = _cos(vecs[i], c) / (math.sqrt(sum(x * x for x in c.values())) or 1.0)
            if s >= score:
                best, score = k, s
        if best is None:
            rest.append([i])
        else:
            multi[best].append(i)
    return _merge(multi, vecs, merge_threshold) + rest


def relate(cands, groups, threshold=0.25):
    """Para cada candidata, o grupo quente mais parecido: (id do grupo ou None, similaridade).

    `groups` é uma lista de (id, matérias). O limiar é mais baixo que o do agrupamento porque uma
    reportagem de fundo se liga ao assunto pelo tema, sem repetir a manchete.
    """
    pool = [it for _, members in groups for it in members]
    vecs = _vectors(pool + cands)
    cents, k = [], 0
    for gid, members in groups:
        c = defaultdict(float)
        for v in vecs[k:k + len(members)]:
            for t, x in v.items():
                c[t] += x
        k += len(members)
        n = math.sqrt(sum(x * x for x in c.values())) or 1.0
        cents.append((gid, {t: x / n for t, x in c.items()}))
    out = []
    for v in vecs[len(pool):]:
        score, gid = max(((_cos(v, c), g) for g, c in cents), default=(0.0, None))
        out.append((gid if score >= threshold else None, score))
    return out


def _merge(groups, vecs, threshold):
    """Junta grupos do mesmo fato que a estrela separou (a fuga de alguém em duas manchetes diferentes).

    O limiar é mais alto que o do agrupamento: com 0,37 já se juntam assuntos distintos da mesma eleição.
    """
    cents = []
    for g in groups:
        c = defaultdict(float)
        for j in g:
            for t, x in vecs[j].items():
                c[t] += x
        n = math.sqrt(sum(x * x for x in c.values())) or 1.0
        cents.append({t: x / n for t, x in c.items()})
    parent = list(range(len(groups)))

    def root(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for a in range(len(groups)):
        for b in range(a + 1, len(groups)):
            if _cos(cents[a], cents[b]) >= threshold:
                parent[root(b)] = root(a)
    merged = defaultdict(list)
    for k, g in enumerate(groups):  # o grupo maior vem antes, então seu centro continua na frente
        merged[root(k)].extend(g)
    return list(merged.values())


# --- Trechos comuns e exclusivos -------------------------------------------------

# Restos de página que o articleBody às vezes traz: legenda de vídeo, crédito, chamadas.
JUNK = re.compile(r"(Crédito:|Edição:|Foto:|Imagem:|Leia (também|mais)|Assine|newsletter|Siga o|Clique aqui|"
                  r"Veja (também|o vídeo)|Ouça|Inscreva-se|WhatsApp|Telegram)", re.I)


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú\"“])", text)
    return [p.strip() for p in parts if len(p.strip()) > 25 and not JUNK.search(p)]


def _shingles(sentence, k=4):
    words = [norm(w) for w in re.findall(r"[\wÀ-ÿ]+", sentence)]
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def split_shared(texts, overlap=0.5):
    """Para {veículo: texto}, separa as frases que aparecem em outros veículos das exclusivas.

    Devolve (comuns, exclusivas): `comuns` é uma lista de (nº de veículos, frase) sem repetição,
    da mais citada para a menos; `exclusivas` mapeia veículo -> frases só dele, na ordem do texto.
    """
    sents = {src: sentences(t) for src, t in texts.items()}
    by_src = {src: set().union(*map(_shingles, ss)) if ss else set() for src, ss in sents.items()}
    owners = defaultdict(set)  # shingle -> veículos que o usam
    for src, shs in by_src.items():
        for sh in shs:
            owners[sh].add(src)
    shared, exclusive, seen = [], {}, []
    for src, ss in sents.items():
        mine = []
        for s in ss:
            shs = _shingles(s)
            hit = sum(1 for sh in shs if owners[sh] - {src}) / (len(shs) or 1)
            if hit < overlap:
                mine.append(s)
                continue
            # Paráfrases do mesmo fato (o lide de cada veículo) entram uma vez só.
            words = set(tokens(s))
            if any(len(words & w) / (len(words | w) or 1) > 0.4 for w in seen):
                continue
            seen.append(words)
            n = 1 + sum(1 for o, oshs in by_src.items() if o != src and len(shs & oshs) / (len(shs) or 1) >= 0.3)
            shared.append((n, s))
        exclusive[src] = mine
    shared.sort(key=lambda x: -x[0])
    return shared, exclusive
