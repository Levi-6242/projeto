# -*- coding: utf-8 -*-
"""Conversa com o GitHub. Mesma ideia do netlify.py: o token manda em tudo.

Por que o GitHub entrou no projeto: a Netlify cobra POR PUBLICAÇÃO (15 créditos de um
total de 300 por mês) e os dados do painel moravam dentro do site publicado -- cada
cadastro novo obrigava a republicar tudo. Em 19/09/2026 isso estourou a conta e travou
as publicações. Aqui, atualizar um arquivo é de graça e sem limite prático.

O DONO DO REPOSITÓRIO É QUEM O TOKEN DISSER. Não há usuário fixo no código: troque o
conteúdo de github_token.txt e o projeto inteiro muda de conta, igual ao Netlify.
"""
from pathlib import Path
import base64
import json
import sys
import urllib.error
import urllib.request

FERR = Path(__file__).resolve().parent
REPO = "projeto"                   # o nome do repositório que guarda o painel
AGENTE = "sal-e-luz-ferramentas"


def token():
    # Rodando dentro do próprio GitHub Actions, a credencial já vem pronta no ambiente.
    import os
    do_ambiente = os.environ.get("GH_TOKEN", "").strip()
    if do_ambiente:
        return do_ambiente

    arq = FERR / "github_token.txt"
    if not arq.exists():
        sys.exit("Falta ferramentas/github_token.txt.\n"
                 "  -> github.com/settings/tokens → Generate new token (classic)\n"
                 "     marque o escopo 'repo' e cole o valor nesse arquivo.")
    valor = arq.read_text(encoding="utf-8").strip()
    if not valor:
        sys.exit("ferramentas/github_token.txt está vazio.")
    return valor


def api(caminho, tok, dados=None, metodo=None):
    req = urllib.request.Request(
        f"https://api.github.com{caminho}",
        data=json.dumps(dados).encode("utf-8") if dados is not None else None,
        headers={"Authorization": f"Bearer {tok}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": AGENTE},
        method=metodo or ("POST" if dados is not None else "GET"))
    try:
        with urllib.request.urlopen(req) as r:
            corpo = r.read()
            return json.loads(corpo) if corpo else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Erro {e.code} em {caminho}: {e.read()[:400]}")


def dono(tok):
    """De quem é este token. É ele que define a conta que hospeda o painel."""
    return api("/user", tok)["login"]


def sha_atual(tok, quem, caminho):
    """O GitHub exige o sha da versão anterior para substituir um arquivo. Se o arquivo
    ainda não existe, não há sha -- e aí é criação, não substituição."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{quem}/{REPO}/contents/{caminho}",
        headers={"Authorization": f"Bearer {tok}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SystemExit(f"Erro {e.code} ao ler {caminho}: {e.read()[:300]}")


def ler(tok, quem, caminho):
    """Conteúdo de um arquivo do repositório, ou None se ele não existe.

    É por aqui que o ciclo descobre o que JÁ está publicado. Guardar isso num arquivo
    local não serviria: o GitHub Actions começa do zero a cada execução e acharia que
    tudo mudou, publicando de 5 em 5 minutos para sempre.
    """
    req = urllib.request.Request(
        f"https://api.github.com/repos/{quem}/{REPO}/contents/{caminho}",
        headers={"Authorization": f"Bearer {tok}",
                 "Accept": "application/vnd.github.raw",
                 "User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(req) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SystemExit(f"Erro {e.code} ao ler {caminho}: {e.read()[:300]}")


def conferir_segredo(conteudo):
    """O repositório é PÚBLICO. Se algum segredo do projeto aparecer dentro do que vai
    subir, para aqui -- no GitHub não adianta apagar depois, porque o histórico guarda
    todas as versões para sempre."""
    for nome in ("netlify_token.txt", "github_token.txt", "senha_painel.txt"):
        arq = FERR / nome
        if not arq.exists():
            continue
        valor = arq.read_text(encoding="utf-8").strip()
        if len(valor) >= 4 and valor.encode("utf-8") in conteudo:
            raise SystemExit(f"ABORTADO -- o conteúdo de {nome} apareceu no arquivo que "
                             f"ia para o repositório público. Nada foi enviado.")


def gravar(tok, quem, caminho, conteudo, mensagem):
    """Cria ou substitui um arquivo no repositório. Devolve True se algo mudou."""
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    conferir_segredo(conteudo)
    corpo = {"message": mensagem,
             "content": base64.b64encode(conteudo).decode("ascii")}
    sha = sha_atual(tok, quem, caminho)
    if sha:
        corpo["sha"] = sha
    api(f"/repos/{quem}/{REPO}/contents/{caminho}", tok, dados=corpo, metodo="PUT")
    return True


def endereco(quem):
    return f"https://{quem}.github.io/{REPO}/painel.html"
