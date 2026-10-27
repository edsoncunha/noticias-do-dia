# Detalhes da skill de notícias

Opções pouco usadas, consultadas só quando o fluxo normal do `SKILL.md` não basta.

## Imagens

O `render` percorre as matérias citadas em cada bloco (`highlight` ou item de `stories`), na ordem `image_id`, `angles` e `sources`, e usa a primeira `og:image` ou imagem do feed que puder ser baixada e não se repetir na edição. A imagem é salva em `edicoes/img/AAAA-MM-DD/` com crédito "Reprodução/Veículo".

- `"image_id": 325` usa primeiro a imagem dessa matéria. Prefira fotos informativas, como o local, as pessoas envolvidas ou um dado, a ilustrações genéricas.
- `"image": false` deixa o bloco sem imagem. Use quando as opções forem violentas, sensacionalistas ou apenas um logotipo.
- `"image": {"url": "https://...", "caption": "Legenda", "credit": "Autor/Agência"}` define a imagem à mão.
- `render --no-images` gera sem imagens, por exemplo sem internet.

## Outros comandos

- `show ID [ID ...] --chars 1200`: texto de matérias fora dos grupos da pauta. Imprime o texto inteiro, então prefira o `dossie`.
- `show --feed ID [ID ...]`: só título, link e resumo do feed.
- `.cache/digest.txt`: índice de todas as manchetes, por veículo, com o grupo de cada uma. Use para procurar um assunto que você saiba ter ficado de fora da pauta, com `grep`, e não para ler inteiro.
- `fetch --deep N`: assuntos por seção com as matérias baixadas (padrão 5). `--min-sources N`: veículos para um assunto entrar na pauta (padrão 2). `--max-pairs N`: assuntos com só 2 veículos listados por seção (padrão 15). `--reuse-hours N`: idade máxima da edição reaproveitada (padrão 3; 0 desliga).

## Manutenção

- Fontes: edite `feeds.json` (`source`, `url` e, opcionalmente, `"hint": "mundo"` para feeds de internacional e `"linha": "direita"` ou `"esquerda"` para a linha editorial mostrada na pauta e priorizada nos dossiês).
- Filtros automáticos: topo de `scripts/noticias.py` (`SPONSORED`, `FOOTBALL_*`, `CELEB_*`, `NOISE`).
- Cliente HTTP (perfis de navegador, retentativas, fallback para o `curl`): `scripts/net.py`.
- Agrupamento por assunto e separação de trechos comuns e exclusivos: `scripts/topics.py`.
- Feeds verificados, inclusive os que não funcionam: `references/feeds.md`.
- O visual segue o New York Times: logotipo em Playfair Display, manchetes em Source Serif 4, corpo em Georgia e rótulos em Libre Franklin, carregadas do Google Fonts.
