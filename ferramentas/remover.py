# -*- coding: utf-8 -*-
"""Tira alguém da lista do painel, de vez.

POR QUE PRECISA DISSO: o GitHub acumula em vez de espelhar -- é o que protege a lista
quando a conta do Netlify muda. O preço é que apagar na origem não basta: o cadastro
continua guardado. Esta ferramenta tira dos DOIS lados, e é por isso que ela existe em
vez de ser "apaga no Netlify e pronto".

  py -3 ferramentas/remover.py "Maria de Souza"        vê o que seria removido
  py -3 ferramentas/remover.py "Maria de Souza" --ok   remove de verdade
  py -3 ferramentas/remover.py --contendo "Teste" --ok remove todos que contenham

Sem --ok ele só mostra. Remover é definitivo: a lista some do painel e o envio some do
Netlify, e não há desfazer.
"""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atualizar_dados
import github
import netlify


def alvos(registros, procurado, por_pedaco):
    if por_pedaco:
        chave = procurado.strip().lower()
        return [r for r in registros if chave in r.get("nome", "").lower()]
    chave = procurado.strip().lower()
    return [r for r in registros if r.get("nome", "").strip().lower() == chave]


def main():
    args = [a for a in sys.argv[1:]]
    confirmar = "--ok" in args
    por_pedaco = "--contendo" in args
    termos = [a for a in args if not a.startswith("--")]
    if not termos:
        sys.exit(__doc__)
    procurado = termos[0]

    senha = atualizar_dados.segredo("senha_painel.txt", "a senha do painel")
    tok_gh = github.token()
    quem = github.dono(tok_gh)

    publicado = github.ler(tok_gh, quem, "dados.enc")
    if not publicado:
        sys.exit("Não há lista publicada.")
    pacote = json.loads(atualizar_dados.decifrar(publicado.decode("ascii"), senha))
    registros = pacote["registros"]

    achados = alvos(registros, procurado, por_pedaco)
    if not achados:
        sys.exit(f"Ninguém com esse nome na lista ({len(registros)} cadastros).")

    print(f"{len(achados)} de {len(registros)} seriam removidos:")
    for r in achados:
        print(f"   {r.get('nome')}  ({r.get('nascimento') or 'sem nascimento'})")

    if not confirmar:
        print("\nNada foi feito. Para remover de verdade, repita com --ok no fim.")
        return 0

    # 1) tirar da lista publicada
    nomes = {r.get("nome", "").strip().lower() for r in achados}
    ficam = [r for r in registros if r.get("nome", "").strip().lower() not in nomes]
    atualizar_dados.gravar(ficam, senha)
    arquivo = Path(__file__).resolve().parent.parent / "dados.enc"
    github.gravar(tok_gh, quem, "dados.enc", arquivo.read_bytes(),
                  f"remove {len(achados)} cadastro(s)")
    print(f"\nlista do painel: {len(registros)} -> {len(ficam)}")

    # 2) tirar da origem, senão o próximo ciclo traz de volta.
    #    A fila de spam entra junto: envio barrado continua existindo lá.
    tok_net = netlify.token()
    sid = netlify.site_id(tok_net)
    apagados = 0
    for f in netlify.api(f"/sites/{sid}/forms", tok_net):
        for estado in ("", "?state=spam"):
            for e in netlify.api(f"/forms/{f['id']}/submissions{estado}", tok_net):
                nome = ((e.get("data") or {}).get("nome") or "").strip().lower()
                bate = (nome in nomes) if not por_pedaco else (procurado.strip().lower() in nome)
                if bate:
                    netlify.api(f"/submissions/{e['id']}", tok_net, metodo="DELETE")
                    apagados += 1
    print(f"envios apagados no Netlify: {apagados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
