import unittest

from app.snmp_client import SnmpError, SnmpNoSuchOid
from snmp_collector import SNMPCollector


class FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.closed = False

    def get_ints(self, oids):
        if oids[0] == "1.3.6.1.2.1.31.1.1.1.6.1" and self.answers.get("fallback"):
            raise SnmpNoSuchOid("HC indisponível")
        if oids[0] == "1.3.6.1.2.1.2.2.1.10.1" and self.answers.get("fallback"):
            return {oids[0]: self.answers["in"], oids[1]: self.answers["out"]}
        if len(oids) == 1 and oids[0].startswith("1.3.6.1.2.1.25.3.3"):
            value = self.answers.get("cpu")
            if value is None:
                raise SnmpNoSuchOid("CPU indisponível")
            return {oids[0]: value}
        return {oids[0]: self.answers["in"], oids[1]: self.answers["out"]}

    def close(self):
        self.closed = True


class TestSNMPCollector(unittest.TestCase):
    def make_collector(self, answers):
        config = {"ip": "127.0.0.1", "porta": 161, "comunidade": "public", "interface": 1,
                  "snmp_version": "2c", "cpu_oid": "1.3.6.1.2.1.25.3.3.1.2.1"}
        collector = SNMPCollector(config)
        collector.client.close()
        collector.client = FakeClient(answers)
        return collector

    def test_primeira_amostra_sem_taxa_e_cpu_valida(self):
        c = self.make_collector({"in": 100, "out": 200, "cpu": 42})
        self.assertEqual(c.coletar_metricas(), (None, None, 42.0))
        c.close()

    def test_contadores_hc_calculam_taxa(self):
        c = self.make_collector({"in": 100, "out": 200, "cpu": 42})
        c.coletar_metricas()
        c.calc.update = lambda *args: type("R", (), {"in_bps": 800.0, "out_bps": 1600.0})()
        self.assertEqual(c.coletar_metricas(), (800.0, 1600.0, 42.0))
        c.close()

    def test_usa_counter32_quando_hc_nao_existe(self):
        c = self.make_collector({"in": 100, "out": 200, "cpu": 42, "fallback": True})
        self.assertEqual(c.coletar_metricas(), (None, None, 42.0))
        self.assertEqual(c.calc.bits, 32)
        c.close()

    def test_cpu_invalida_nao_vira_zero(self):
        c = self.make_collector({"in": 100, "out": 200, "cpu": 150})
        with self.assertRaises(SnmpError):
            c.coletar_metricas()
        c.close()


if __name__ == "__main__":
    unittest.main()
