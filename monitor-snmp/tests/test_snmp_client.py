import asyncio
import unittest
from unittest.mock import patch

from app.snmp_client import SnmpClient, SnmpError, SnmpTimeout


class TestSnmpClient(unittest.TestCase):
    def test_cancelamento_e_convertido_em_erro_snmp_controlado(self):
        client = SnmpClient({"host": "127.0.0.1"})
        try:
            def cancel(coroutine, timeout):
                coroutine.close()
                raise asyncio.CancelledError

            with patch("app.snmp_client.asyncio.wait_for", side_effect=cancel):
                with self.assertRaises(SnmpTimeout):
                    client.get(["1.3.6.1.2.1.1.1.0"])
        finally:
            client.close()

    def test_cliente_fechado_nao_inicia_nova_consulta(self):
        client = SnmpClient({"host": "127.0.0.1"})
        client.close()
        client.close()  # close pode ser chamado mais de uma vez
        with self.assertRaises(SnmpError):
            client.get(["1.3.6.1.2.1.1.1.0"])


if __name__ == "__main__":
    unittest.main()
