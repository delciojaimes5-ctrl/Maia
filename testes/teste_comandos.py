"""
Testes da compreensão de comandos da Maiia.

Correr sem servidor, sem base de dados e sem Arduino:

    python testes/teste_comandos.py
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import types


def _modulo_falso(nome, **atributos):
    """Maiia importa groq/edge_tts; os testes não precisam deles."""

    if nome in sys.modules:
        return

    modulo = types.ModuleType(nome)

    for chave, valor in atributos.items():
        setattr(modulo, chave, valor)

    sys.modules[nome] = modulo


_modulo_falso("groq", Groq=object)
_modulo_falso("dotenv", load_dotenv=lambda *a, **k: None)
_modulo_falso("edge_tts", Communicate=object)

from assistente.comandos import planear_comandos  # noqa: E402
from assistente import maiia  # noqa: E402


def comandos(frase):
    return planear_comandos(frase)["comandos"]


class TesteComandos(unittest.TestCase):
    """Casos recolhidos da auditoria (2026-11-22)."""

    # -------------------------------------------------
    # Formulações que falhavam
    # -------------------------------------------------

    def test_imperativo_formal(self):
        self.assertEqual(
            comandos("ligue a primeira lâmpada"), ["LAMP1_ON"]
        )

    def test_erro_de_transcricao(self):
        self.assertEqual(
            comandos("ascende a primeira luz"), ["LAMP1_ON"]
        )

    def test_participio(self):
        self.assertEqual(
            comandos("quero a primeira ligada"), ["LAMP1_ON"]
        )

    def test_coloquial(self):
        self.assertEqual(
            comandos("bota a primeira acesa"), ["LAMP1_ON"]
        )

    # -------------------------------------------------
    # Multi-alvo
    # -------------------------------------------------

    def test_duas_lampadas(self):
        self.assertEqual(
            comandos("liga a primeira e a segunda"),
            ["LAMP1_ON", "LAMP2_ON"]
        )

    def test_duas_accoes(self):
        self.assertEqual(
            comandos("liga a primeira e desliga a segunda"),
            ["LAMP1_ON", "LAMP2_OFF"]
        )

    def test_exclusao(self):
        self.assertEqual(
            comandos("desliga todas menos a primeira"),
            ["LAMP2_OFF", "LAMP3_OFF"]
        )

    # -------------------------------------------------
    # Negação por cláusula
    # -------------------------------------------------

    def test_negacao_nao_cancela_frase(self):
        self.assertEqual(
            comandos("não sei, liga a primeira"), ["LAMP1_ON"]
        )

    def test_negacao_directa_e_ambigua(self):
        plano = planear_comandos("não ligues a primeira")
        self.assertTrue(plano["ambiguo"])
        self.assertEqual(plano["comandos"], [])

    # -------------------------------------------------
    # Perguntas nunca executam
    # -------------------------------------------------

    def test_pergunta_nao_executa(self):
        plano = planear_comandos("está tudo ligado?")
        self.assertTrue(plano["pergunta"])
        self.assertEqual(plano["comandos"], [])

    def test_pergunta_sem_pontuacao(self):
        plano = planear_comandos("quais estão ligadas")
        self.assertTrue(plano["pergunta"])

    # -------------------------------------------------
    # Regressões da versão anterior (devem continuar certas)
    # -------------------------------------------------

    def test_basico(self):
        self.assertEqual(
            comandos("liga a primeira lâmpada"), ["LAMP1_ON"]
        )

    def test_numero_digito(self):
        self.assertEqual(comandos("liga a luz 1"), ["LAMP1_ON"])

    def test_todas_um_comando(self):
        self.assertEqual(comandos("apaga tudo"), ["ALL_OFF"])

    def test_todas_as_luzes(self):
        self.assertEqual(
            comandos("desliga todas as luzes"), ["ALL_OFF"]
        )

    def test_terceira(self):
        self.assertEqual(
            comandos("liga por favor a terceira"), ["LAMP3_ON"]
        )

    def test_lampadas_plural_e_todas(self):
        self.assertEqual(comandos("liga as lâmpadas"), ["ALL_ON"])

    def test_acao_sem_alvo(self):
        plano = planear_comandos("liga")
        self.assertEqual(plano["comandos"], [])
        self.assertEqual(plano["pendente"], "ON")

    def test_alvo_sem_acao(self):
        plano = planear_comandos("a segunda")
        self.assertEqual(plano["alvos"], ["LAMP2"])

    def test_leva_a_serie_de_lampadas(self):
        self.assertEqual(
            comandos("desliga a lâmpada número dois"), ["LAMP2_OFF"]
        )

    # -------------------------------------------------
    # Segurança: nunca executar metade nem inventar
    # -------------------------------------------------

    def test_acao_sem_alvo_com_outro_comando(self):
        plano = planear_comandos("liga a primeira e desliga")
        self.assertTrue(plano["ambiguo"])
        self.assertEqual(plano["comandos"], [])

    def test_duas_accoes_sem_alvo(self):
        plano = planear_comandos("liga e desliga")
        self.assertTrue(plano["ambiguo"])

    def test_texto_sem_comando(self):
        plano = planear_comandos("bom dia, tudo bem")
        self.assertEqual(plano["comandos"], [])
        self.assertFalse(plano["ambiguo"])



class TesteSemTolerancia(unittest.TestCase):
    """
    Sem distância de edição: nenhuma destas frases pode acender ou
    apagar uma lâmpada (revisão da PR #2, 2026-11-22).
    """

    def test_acesso_nao_e_aceso(self):
        self.assertEqual(comandos("quero acesso à primeira sala"), [])

    def test_pagar_nao_e_apagar(self):
        self.assertEqual(
            comandos("vou pagar a segunda prestação"), []
        )

    def test_conta_nao_e_corta(self):
        self.assertEqual(comandos("conta a primeira história"), [])

    def test_fecha_a_porta_nao_escolhe_lampada(self):
        plano = planear_comandos("fecha a porta")
        self.assertEqual(plano["comandos"], [])
        self.assertEqual(plano["pendente"], "OFF")

    def test_liga_a_tv_nao_escolhe_lampada(self):
        plano = planear_comandos("liga a tv")
        self.assertEqual(plano["comandos"], [])
        self.assertEqual(plano["pendente"], "ON")

    def test_lugar_nao_e_ligar(self):
        plano = planear_comandos("não tenho lugar para a primeira")
        self.assertEqual(plano["comandos"], [])
        self.assertFalse(plano["ambiguo"])

    def test_passado_nao_e_ordem(self):
        self.assertEqual(
            comandos("eu liguei a primeira ontem"), []
        )

    def test_conjuntivo_explicito_continua_a_valer(self):
        self.assertEqual(
            comandos("desligues a primeira"), ["LAMP1_OFF"]
        )


class TesteCardinais(unittest.TestCase):
    """Cardinal solto não é lâmpada; só depois de lâmpada/luz/número."""

    def test_uma_musica(self):
        self.assertEqual(comandos("bota uma música"), [])

    def test_dois_minutos(self):
        self.assertEqual(
            comandos("liga a segunda daqui a um minuto"), ["LAMP2_ON"]
        )

    def test_dois_segundos(self):
        self.assertEqual(
            comandos("liga a primeira por dois segundos"), ["LAMP1_ON"]
        )

    def test_as_duas_nao_liga_a_segunda(self):
        plano = planear_comandos("liga as duas")
        self.assertEqual(plano["comandos"], [])
        self.assertEqual(plano["pendente"], "ON")

    def test_cardinal_depois_de_numero(self):
        self.assertEqual(
            comandos("acende a luz número dois"), ["LAMP2_ON"]
        )

    def test_cardinal_depois_de_lampada(self):
        self.assertEqual(comandos("liga a lâmpada 3"), ["LAMP3_ON"])


class TesteExclusaoEmClausulas(unittest.TestCase):
    """A exclusão sobrevive à separação em cláusulas."""

    def test_exclusao_depois_de_virgula(self):
        self.assertEqual(
            comandos("liga todas, menos a primeira"),
            ["LAMP2_ON", "LAMP3_ON"]
        )

    def test_exclusao_alargada_por_clausula_de_alvo(self):
        self.assertEqual(
            comandos("desliga todas menos a primeira e a segunda"),
            ["LAMP3_OFF"]
        )


class TestePerguntas(unittest.TestCase):
    """Pedido educado executa; pergunta sobre o estado não."""

    def test_pedido_educado_executa(self):
        self.assertEqual(
            comandos("podes ligar a primeira luz?"), ["LAMP1_ON"]
        )

    def test_pedido_educado_com_tudo(self):
        self.assertEqual(
            comandos("consegues desligar tudo?"), ["ALL_OFF"]
        )

    def test_estabem_e_confirmacao(self):
        self.assertEqual(
            comandos("está bem, liga a primeira"), ["LAMP1_ON"]
        )

    def test_pergunta_so_com_participio(self):
        plano = planear_comandos("está tudo ligado?")
        self.assertTrue(plano["pergunta"])
        self.assertEqual(plano["comandos"], [])

    def test_primeira_ligada_e_aceita_por_agora(self):
        # Registado na revisão: "a primeira está ligada" executa ON.
        self.assertEqual(
            comandos("a primeira está ligada"), ["LAMP1_ON"]
        )


class TesteRepeticoes(unittest.TestCase):
    """Comandos repetidos deduplicados; contraditórios ambíguos."""

    def test_ligar_e_desligar_a_mesma(self):
        plano = planear_comandos("liga a primeira e desliga a primeira")
        self.assertTrue(plano["ambiguo"])
        self.assertEqual(plano["comandos"], [])

    def test_repetido_uma_vez(self):
        self.assertEqual(
            comandos("liga a primeira e liga a primeira"), ["LAMP1_ON"]
        )

    def test_alvo_implicito_em_all(self):
        self.assertEqual(comandos("liga tudo e a primeira"), ["ALL_ON"])


class TesteExecucao(unittest.TestCase):
    """executar_comandos diz a causa real da falha."""

    def test_sem_controlo(self):
        self.assertEqual(
            maiia.executar_comandos(["LAMP1_ON"], None),
            maiia.SEM_CONTROLO
        )

    def test_falha_de_ligacao(self):
        def levanta(comando):
            raise ConnectionError("sem porta")

        self.assertEqual(
            maiia.executar_comandos(["LAMP1_ON"], levanta),
            maiia.FALHA_LIGACAO
        )

    def test_falha_de_execucao(self):
        def levanta(comando):
            raise RuntimeError("resposta inválida")

        self.assertEqual(
            maiia.executar_comandos(["LAMP1_ON"], levanta),
            maiia.FALHA_EXECUCAO
        )

    def test_parcial(self):
        def executar(comando):
            if comando == "LAMP2_ON":
                raise ConnectionError("sem porta")

        resposta = maiia.executar_comandos(
            ["LAMP1_ON", "LAMP2_ON"], executar
        )

        self.assertIn("A primeira lâmpada está ligada.", resposta)
        self.assertIn("não consegui confirmar com o Arduino", resposta)

    def test_sem_comandos(self):
        self.assertIn(
            "nenhum comando", maiia.executar_comandos([], None)
        )


if __name__ == "__main__":

    unittest.main(verbosity=2)
