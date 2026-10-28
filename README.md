# noticias-do-dia

Skill de agente que monta uma edição diária de notícias a partir dos feeds RSS dos principais veículos brasileiros. O boletim cobre amplamente o espectro editorial e não só a imprensa tradicional, possibilitando ao leitor ou leitora o acesso ao contraditório.

## Instalar o Python

A skill requer Python 3.9 ou mais recente e acesso à internet.

- **Windows:** `winget install Python.Python.3.12`, ou o instalador de [python.org](https://www.python.org/downloads/) com a opção *Add python.exe to PATH* marcada.
- **macOS:** `brew install python`, ou o instalador de [python.org](https://www.python.org/downloads/).
- **Linux:** já vem instalado na maioria das distribuições. Se não vier, use `sudo apt install python3` ou equivalente.

## Habilitar a skill

A skill segue o formato aberto [Agent Skills](https://agentskills.io) e fica em `skills/noticias/`. Coloque essa pasta no diretório de skills do seu agente. No Claude Code:

```sh
# macOS e Linux
ln -s "$PWD/skills/noticias" ~/.claude/skills/noticias
```

```powershell
# Windows (PowerShell)
Copy-Item -Recurse skills\noticias "$HOME\.claude\skills\noticias"
```

Agentes sem suporte a skills podem usar o `AGENTS.md` da raiz, abrindo o agente nesta pasta.

## Gerar as notícias do dia

Pergunte ao agente: **"quais as notícias?"**

A edição é salva em `~/noticias/edicoes/AAAA-MM-DD.html` (no Windows, `%USERPROFILE%\noticias\edicoes\`) e aberta no navegador. Para usar outra pasta, defina a variável `NOTICIAS_DIR`.

## Como a skill economiza tokens

A coleta é toda feita por scripts locais em `skills/noticias/scripts/`, e o modelo só entra para escrever a edição:

- `net.py` baixa feeds e páginas com retentativas, backoff exponencial, troca de perfil de navegador (User-Agent e cabeçalhos coerentes com ele), detecção de páginas anti-robô e fallback para o `curl`.
- `topics.py` agrupa as manchetes por assunto e separa, no texto das matérias, os fatos que vários veículos repetem do que cada um traz de exclusivo.
- `noticias.py fetch` grava uma pauta compacta com os assuntos agrupados e os dossiês dos dois assuntos mais cobertos, e já baixa as matérias dos demais assuntos de destaque. Se já houver edição de hoje com menos de 3 horas, ele só a reabre.
- O modelo lê a pauta numa única leitura, pede outros dossiês só se precisar (`noticias.py dossie B4`, que sai do cache) e grava o JSON editorial que o `render` transforma em HTML.
- No Claude Code, a skill roda com o Sonnet (`model: sonnet` no `SKILL.md`), que basta para o trabalho editorial e custa menos. A sessão volta ao modelo anterior na mensagem seguinte. Para usar outro modelo, mude ou apague essa linha.
