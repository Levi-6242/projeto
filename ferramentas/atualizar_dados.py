# -*- coding: utf-8 -*-
"""Baixa os cadastros do Netlify e grava `dados.enc`, que o painel lê.

Por que cifrado: o arquivo vai para o ar junto com o site, e ali estão nome, telefone,
endereço e aniversário de gente de verdade. Publicar isso aberto seria vazar a lista da
igreja. Com AES-GCM e a senha do painel, quem baixar o arquivo sem a senha tem só ruído.

Por que assim, e não uma função no servidor: o deploy deste site é arrastar a pasta, e
deploy manual não leva funções. Este caminho mantém o deploy como está.

O QUE PRECISA, uma vez só:
  1. ferramentas/netlify_token.txt  -- token pessoal do Netlify (NÃO vai para o ar).
     Gere em app.netlify.com → User settings → Applications → Personal access tokens.
  2. ferramentas/senha_painel.txt   -- a senha que o pastor vai digitar (NÃO vai para o ar).

Uso: py -3 ferramentas/atualizar_dados.py
"""
from datetime import date
from pathlib import Path
import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import netlify

RAIZ = Path(__file__).resolve().parent.parent
FERR = RAIZ / "ferramentas"
CIFRADO = RAIZ / "dados.enc"     # quando existe senha
ABERTO = RAIZ / "dados.json"     # quando não existe senha
ITERACOES = 210_000   # mesmo número no painel; PBKDF2-SHA256

# Campos que o painel usa. Tudo que não estiver aqui não sai do Netlify -- o arquivo
# publicado não carrega e-mail nem consentimento à toa.
CAMPOS = ("nome", "nascimento", "whatsapp", "endereco", "bairro", "departamento", "como")


# Cada segredo tem um arquivo aqui no computador e uma variável correspondente na
# nuvem, onde arquivo não existe e o valor vem dos Secrets do GitHub.
NO_AMBIENTE = {"senha_painel.txt": "PAINEL_SENHA"}


def segredo(nome, descricao):
    import os
    do_ambiente = os.environ.get(NO_AMBIENTE.get(nome, ""), "").strip()
    if do_ambiente:
        return do_ambiente

    caminho = FERR / nome
    if not caminho.exists():
        sys.exit(f"Falta {caminho.name} em ferramentas/.\n  -> {descricao}")
    valor = caminho.read_text(encoding="utf-8").strip()
    if not valor:
        sys.exit(f"{caminho.name} está vazio.")
    return valor


def baixar(token):
    sid = netlify.site_id(token)
    formularios = netlify.api(f"/sites/{sid}/forms", token)
    registros = []
    for f in formularios:
        nome_form = (f.get("name") or "").lower()
        envios = netlify.api(f"/forms/{f['id']}/submissions?per_page=1000", token)
        for e in envios:
            dados = e.get("data") or {}
            reg = {c: str(dados.get(c, "")).strip() for c in CAMPOS if dados.get(c)}
            if not reg.get("nome"):
                continue
            reg["tipo"] = "visitante" if "visitante" in nome_form else "membro"
            registros.append(reg)
        print(f"  {f.get('name'):12s} {len(envios):>4d} envio(s)")
    return registros


def cifrar(texto, senha):
    """salt(16) + nonce(12) + cifra, tudo junto em base64. O painel faz o inverso."""
    salt = os.urandom(16)
    nonce = os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                       iterations=ITERACOES).derive(senha.encode("utf-8"))
    cifra = AESGCM(chave).encrypt(nonce, texto.encode("utf-8"), None)
    return base64.b64encode(salt + nonce + cifra).decode("ascii")


def decifrar(b64, senha):
    """O inverso de cifrar(). Usado para ler o histórico herdado."""
    bruto = base64.b64decode(b64)
    salt, nonce, cifra = bruto[:16], bruto[16:28], bruto[28:]
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                       iterations=ITERACOES).derive(senha.encode("utf-8"))
    return AESGCM(chave).decrypt(nonce, cifra, None).decode("utf-8")


def juntar(guardados, chegando):
    """O GitHub ACUMULA; o Netlify é só a porta de entrada.

    A lista publicada nunca é substituída pelo que o Netlify devolve -- ela só cresce.
    Quem já está guardado continua guardado mesmo que suma da origem.

    Isso nasceu de um problema real: em 20/09/2026 o site passou para outra conta do
    Netlify e os formulários novos nasceram vazios. Se o ciclo espelhasse a origem, os
    51 cadastros de então teriam sido apagados do painel no primeiro ciclo depois da
    troca. Acumulando, uma conta nova (ou perdida) não leva ninguém junto.

    A mesma pessoa não entra duas vezes: a comparação é por nome + nascimento.
    """
    def chave(r):
        return (r.get("nome", "").strip().lower(), r.get("nascimento", "").strip())

    vistos = {chave(r) for r in guardados}
    return guardados + [r for r in chegando if chave(r) not in vistos]


def impressao(registros):
    """Assinatura da lista: muda quando um cadastro entra, sai ou é corrigido, e NÃO
    muda quando o Netlify devolve os mesmos envios em outra ordem.

    Comparar o dados.enc pronto não serviria: o AES-GCM sorteia salt e nonce novos a
    cada cifragem, então o arquivo sai diferente mesmo com a lista idêntica.
    """
    ordenado = sorted(registros, key=lambda r: (r.get("nome", ""), r.get("nascimento", ""),
                                                r.get("whatsapp", "")))
    bruto = json.dumps(ordenado, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def gravar(registros, senha):
    """Grava a lista no arquivo que o painel lê. Devolve (arquivo, como ficou)."""
    conteudo = json.dumps({"atualizado": date.today().isoformat(),
                           "registros": registros}, ensure_ascii=False)

    # Só um dos dois arquivos pode ficar na pasta: o painel procura o cifrado primeiro,
    # e um sobrando faria ele pedir senha depois de a senha ter saído (ou o contrário).
    if registros:
        CIFRADO.write_text(cifrar(conteudo, senha), encoding="ascii")
        ABERTO.unlink(missing_ok=True)
        return CIFRADO, "cifrado -- o painel pede a senha"
    ABERTO.write_text(conteudo, encoding="utf-8")
    CIFRADO.unlink(missing_ok=True)
    return ABERTO, "lista vazia, sem nada a proteger -- o painel abre direto"


def main():
    token = netlify.token()
    senha = segredo("senha_painel.txt", "a senha que o pastor vai digitar no painel")
    # A proteção acompanha o risco. Lista vazia não tem o que proteger, então o painel
    # abre direto -- foi o "sem senha por ora" combinado com o Levi em 14/09, com a base
    # recém-limpa. No instante em que entrar o primeiro cadastro, a lista volta a subir
    # cifrada sozinha: ninguém precisa lembrar de religar nada.

    print("baixando os cadastros...")
    registros = baixar(token)
    if not registros:
        # Não abortar: sem cadastro nenhum, o certo é publicar uma lista VAZIA. Abortar
        # deixaria no ar o dados.enc anterior, e o painel seguiria mostrando gente que
        # já foi apagada do Netlify.
        print("  (nenhum cadastro -- vai ser gravada uma lista vazia)")

    saida, como = gravar(registros, senha)

    membros = sum(1 for r in registros if r["tipo"] == "membro")
    print(f"\n{len(registros)} cadastros ({membros} membros) -> {saida.name}, "
          f"{saida.stat().st_size} bytes, {como}")
    print("agora rode: py -3 ferramentas/publicar.py")


if __name__ == "__main__":
    main()
