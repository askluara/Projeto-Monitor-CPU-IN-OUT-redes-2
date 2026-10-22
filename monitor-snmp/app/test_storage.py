import os
import sqlite3
import tempfile
import unittest

from app.storage import Storage


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.db = Storage(self.path)

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        self.dir.cleanup()

    def test_grava_e_le(self):
        self.db.add_sample(100.0, 200.0, 5.0, ts=1000)
        self.assertEqual(self.db.query_samples(), [(1000, 100.0, 200.0, 5.0, None)])

    def test_filtro_periodo(self):
        for t in (100, 200, 300, 400):
            self.db.add_sample(t, t, 1.0, ts=t)
        rows = self.db.query_samples(200, 300)
        self.assertEqual([r[0] for r in rows], [200, 300])

    def test_sem_dados_no_periodo(self):
        self.db.add_sample(1, 1, 1, ts=100)
        self.assertEqual(self.db.query_samples(500, 600), [])

    def test_aceita_nulos(self):
        self.db.add_sample(None, None, 7.0, ts=1)
        self.assertEqual(self.db.query_samples()[0], (1, None, None, 7.0, None))

    def test_persiste_limite_cpu_usado_na_amostra(self):
        self.db.add_sample(100, 200, 5, ts=123, cpu_threshold=2)
        self.assertEqual(self.db.query_samples()[0], (123, 100, 200, 5, 2))

    def test_migra_banco_antigo_sem_perder_amostras(self):
        legacy_path = os.path.join(self.dir.name, "legacy.db")
        legacy = sqlite3.connect(legacy_path)
        legacy.execute(
            "CREATE TABLE samples (id INTEGER PRIMARY KEY, ts REAL, in_bps REAL, out_bps REAL, cpu REAL)"
        )
        legacy.execute("INSERT INTO samples VALUES (1, 123, 100, 200, 5)")
        legacy.commit()
        legacy.close()

        migrated = Storage(legacy_path)
        self.assertEqual(migrated.query_samples(), [(123, 100, 200, 5, None)])
        migrated.close()

    def test_ordem_cronologica(self):
        self.db.add_sample(1, 1, 1, ts=300)
        self.db.add_sample(1, 1, 1, ts=100)
        self.assertEqual([r[0] for r in self.db.query_samples()], [100, 300])

    def test_persiste_apos_reabrir(self):
        self.db.add_sample(10, 20, 30, ts=5)
        self.db.close()
        db2 = Storage(self.path)
        self.assertEqual(db2.count_samples(), 1)
        db2.close()

    def test_erros_e_alertas(self):
        self.db.add_error("SnmpTimeout", "sem resposta", ts=1)
        self.db.add_alert_event("cpu", 90.0, 80.0, "popup,email", "x", ts=2)
        self.assertEqual(self.db.query_errors()[0][1], "SnmpTimeout")
        self.assertEqual(self.db.query_alert_events()[0][1], "cpu")

    def test_filtra_eventos_de_alerta_por_periodo(self):
        for ts in (100, 200, 300):
            self.db.add_alert_event("cpu", 90.0, 80.0, "popup", "limite", ts=ts)
        rows = self.db.query_alert_events(start=150, end=250)
        self.assertEqual([(row[0], row[1]) for row in rows], [(200, "cpu")])


if __name__ == "__main__":
    unittest.main()
