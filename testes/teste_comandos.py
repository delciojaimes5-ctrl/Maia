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

from assistente.comandos import planear_comandos  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
