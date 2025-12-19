## Setup dev environment

### Linux or Git Bash on Windows

```bash
curl -fsSL https://deno.land/install.sh | sh    # install Deno JS Runtime https://github.com/yt-dlp/yt-dlp/wiki/EJS
poetry config virtualenvs.in-project true       # virtualenv in the same directory
poetry install                                  # install dependancy packages
poetry run gridplayer                           # run
```
