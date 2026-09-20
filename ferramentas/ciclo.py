# -*- coding: utf-8 -*-
"""O ciclo inteiro em UM comando: baixa os cadastros e atualiza o painel se algo mudou.

POR QUE O PAINEL SAIU DA NETLIFY (19/09/2026): lá cada publicação custa 15 créditos de
um total de 300 por mês, e a lista morava DENTRO do site publicado -- ou seja, cada
cadastro novo obrigava a republicar o site inteiro. Com os cartazes funcionando, a conta
estourou em quatro dias e as publicações foram bloqueadas. Agora a lista vive no GitHub,
onde atualizar arquivo é de graça: cadastro novo custa zero.

A DIVISÃO ATUAL:
  - Netlify = as páginas de cadastro. Os cartazes impressos apontam para lá, então esses
              endereços não podem mudar. Só é republicada quando o HTML muda, na mão,
              com `publicar.py --enviar`.
  - GitHub  = o painel do pastor e a lista. Muda o tempo todo, sozinho, aqui.

O painel não precisou de nenhuma alteração: ele busca `dados.enc` por caminho relativo,
então funciona igual em qualquer hospedagem, desde que os dois fiquem lado a lado.

Uso:
  pythonw ferramentas/ciclo.py     silencioso, é o que a tarefa agendada roda
  py -3   ferramentas/ciclo.py     igual, mas mostrando o que aconteceu na tela
"""
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atualizar_dados
import github
import netlify

FERR = Path(__file__).resolve().parent
ASSINATURA = "ultima_lista.txt"   # mora NO REPOSITÓRIO, ao lado da lista
LOG = FERR / "log-automacao.txt"


def registrar(mensagem):
    """Só eventos de verdade entram no log: atualizou ou falhou.

    Ciclo sem novidade não escreve nada. Rodando a cada 5 minutos, uma linha por ciclo
    daria quase 300 linhas por dia de "não fiz nada" e esconderia o que importa.

    Erro repetido também não se repete: uma falha permanente (token vencido, internet
    fora) encheria o arquivo de linhas idênticas até ninguém achar mais nada. A primeira
    aparição basta para saber o que houve e desde quando.
    """
    if LOG.exists():
        linhas = LOG.read_text(encoding="utf-8").rstrip().split("\n")
        if linhas and linhas[-1].endswith(mensagem):
            return
    with LOG.open("a", encoding="utf-8") as arq:
        arq.write(f"{datetime.now():%d/%m/%Y %H:%M}  {mensagem}\n")


def main():
    try:
        tok_netlify = netlify.token()
        tok_github = github.token()
        quem = github.dono(tok_github)
        senha = atualizar_dados.segredo("senha_painel.txt",
                                        "a senha que o pastor vai digitar no painel")
        registros = atualizar_dados.baixar(tok_netlify)

        agora = atualizar_dados.impressao(registros)
        publicada = github.ler(tok_github, quem, ASSINATURA)
        antes = publicada.decode("ascii").strip() if publicada else ""
        if agora == antes:
            print("sem novidade -- nada enviado")
            return 0

        arquivo, _ = atualizar_dados.gravar(registros, senha)
        github.gravar(tok_github, quem, arquivo.name, arquivo.read_bytes(),
                      f"{len(registros)} cadastros")

        # A assinatura só é gravada DEPOIS de a lista subir. Se o envio da lista falhar,
        # ela continua velha e o próximo ciclo tenta de novo em 5 minutos.
        github.gravar(tok_github, quem, ASSINATURA, agora, f"assinatura de {len(registros)}")
        membros = sum(1 for r in registros if r["tipo"] == "membro")
        registrar(f"painel atualizado: {len(registros)} cadastros ({membros} membros)")
        print(f"painel atualizado: {len(registros)} cadastros")
        return 0

    except (Exception, SystemExit) as erro:
        # SystemExit entra junto de propósito: netlify.token(), github.token() e
        # segredo() avisam o que falta chamando sys.exit(), e sem console essa mensagem
        # se perderia no ar.
        registrar(f"ERRO: {erro}")
        print(f"ERRO: {erro}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
