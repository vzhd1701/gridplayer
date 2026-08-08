$ErrorActionPreference = 'SilentlyContinue'
Get-Process '{APP_NAME}*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
