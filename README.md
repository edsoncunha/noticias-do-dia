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
