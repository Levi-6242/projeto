# -*- coding: utf-8 -*-
"""Conversa com o Netlify: token, achar o site e chamar a API.

Por que existe: o identificador do site estava escrito dentro de dois scripts. Trocar a
conta do Netlify (por exemplo, passar o projeto para uma conta da igreja) obrigaria a
caçar esse número em cada arquivo. Aqui o site é encontrado **pelo nome**, então trocar
de conta passa a ser: gerar um token novo, colar em netlify_token.txt e pronto.
"""
from pathlib import Path
import json
import sys
import urllib.error
import urllib.request

FERR = Path(__file__).resolve().parent
NOME_SITE = "igreja-saleluz"     # o que vem antes de .netlify.app
# 15/09: o projeto passou para a conta da igreja. O site antigo "sal-e-luz", na conta
# pessoal do Levi, deixou de ser o oficial.
AGENTE = "sal-e-luz-ferramentas"


def token():
    # Na nuvem (GitHub Actions) não existe arquivo: a credencial vem dos Secrets, pelo
    # ambiente. No computador, continua vindo do arquivo, como sempre foi.
    import os
    do_ambiente = os.environ.get("NETLIFY_TOKEN", "").strip()
    if do_ambiente:
        return do_ambiente

    arq = FERR / "netlify_token.txt"
    if not arq.exists():
        sys.exit("Falta ferramentas/netlify_token.txt.\n"
                 "  -> app.netlify.com → User settings → Applications → Personal access tokens")
    valor = arq.read_text(encoding="utf-8").strip()
    if not valor:
        sys.exit("netlify_token.txt está vazio.")
    return valor


def api(caminho, tok, dados=None, tipo=None, metodo=None):
    cab = {"Authorization": "Bearer " + tok, "User-Agent": AGENTE}
    if tipo:
        cab["Content-Type"] = tipo
    req = urllib.request.Request("https://api.netlify.com/api/v1" + caminho,
                                 data=dados, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            corpo = r.read().decode("utf-8")
            return json.loads(corpo) if corpo.strip() else None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("O Netlify recusou o token (401). Gere outro e cole em "
                     "ferramentas/netlify_token.txt.")
        sys.exit(f"Erro {e.code} em {caminho}: {e.read()[:300]}")


def site_id(tok):
    """Acha o site pelo nome, dentro da conta a que o token pertence."""
    sites = api("/sites", tok)
    for s in sites:
        if s.get("name") == NOME_SITE:
            return s["id"]
    # Mensagem útil em vez de "não achei": quase sempre o token é de outra conta, ou o
    # site foi criado com outro nome.
    nomes = ", ".join(sorted(s.get("name", "?") for s in sites)) or "(nenhum)"
    sys.exit(f'Não achei um site chamado "{NOME_SITE}" nesta conta do Netlify.\n'
             f"  Sites que este token enxerga: {nomes}\n"
             f"  Ou o token é de outra conta, ou o site tem outro nome "
             f"(ajuste NOME_SITE em ferramentas/netlify.py).")
