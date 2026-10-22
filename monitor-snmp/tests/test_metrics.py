import unittest
from app.metrics import RateCalculator, MAX32, clamp_percent


class TestRate(unittest.TestCase):
    def test_primeira_leitura_none(self):
        self.assertIsNone(RateCalculator().update(0, 0, 0))

    def test_calculo_basico(self):
        c = RateCalculator()
        c.update(0.0, 1000, 2000)
        r = c.update(2.0, 1000 + 250, 2000 + 500)
        self.assertAlmostEqual(r.in_bps, 1000)   # 250*8/2
        self.assertAlmostEqual(r.out_bps, 2000)

    def test_usa_intervalo_real(self):
        c = RateCalculator()
        c.update(0.0, 0, 0)
        r = c.update(10.0, 1250, 0)  # coleta atrasou: 10s e nao 5s
        self.assertAlmostEqual(r.in_bps, 1000)

    def test_reset_64_bits_descarta(self):
        c = RateCalculator(64)
        c.update(0, 10_000, 10_000)
        self.assertIsNone(c.update(1, 50, 50))

    def test_wrap_32_bits(self):
        c = RateCalculator(32, max_plausible_bps=1e10)
        c.update(0, MAX32 - 1000, 0)
        r = c.update(1, 1000, 0)  # delta = 2000 bytes
        self.assertAlmostEqual(r.in_bps, 16000)

    def test_taxa_absurda_descartada(self):
        c = RateCalculator(32, max_plausible_bps=1e6)
        c.update(0, 5000, 0)
        self.assertIsNone(c.update(1, 10, 0))  # "wrap" geraria ~34 Gbps

    def test_intervalo_invalido(self):
        c = RateCalculator()
        c.update(5, 0, 0)
        self.assertIsNone(c.update(5, 100, 100))

    def test_reset_state(self):
        c = RateCalculator()
        c.update(0, 0, 0)
        c.reset_state()
        self.assertIsNone(c.update(1, 100, 100))

    def test_cpu(self):
        self.assertEqual(clamp_percent(37), 37.0)
        self.assertIsNone(clamp_percent(150))
        self.assertIsNone(clamp_percent(-1))


if __name__ == "__main__":
    unittest.main()
