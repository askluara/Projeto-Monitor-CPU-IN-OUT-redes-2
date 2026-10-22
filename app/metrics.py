"""Calculo de taxa (bps) a partir de contadores SNMP acumulados.

bps = (delta_bytes * 8) / intervalo_real_em_segundos

Casos tratados (a funcao devolve None em vez de uma taxa invalida):
  * primeira leitura (nao ha anterior);
  * reinicio do contador (Counter64 diminuiu);
  * wrap de Counter32 (diminuiu, mas e compativel com a velocidade do link);
  * troca de interface (reset_state);
  * intervalo nulo/negativo;
  * taxa acima do limite plausivel.
"""
from dataclasses import dataclass
from typing import Optional

MAX32 = 2 ** 32
MAX64 = 2 ** 64


@dataclass
class Rate:
    in_bps: float
    out_bps: float


class RateCalculator:
    def __init__(self, counter_bits: int = 64, max_plausible_bps: float = 1e10):
        self.bits = counter_bits
        self.max_bps = max_plausible_bps
        self.reset_state()

    def reset_state(self):
        """Descarta a leitura anterior (usar ao trocar interface/equipamento)."""
        self._prev = None  # (t_monotonic, in_bytes, out_bytes)

    def _delta(self, cur: int, prev: int) -> Optional[int]:
        if cur >= prev:
            return cur - prev
        # contador diminuiu: wrap (32 bits) ou reinicio
        if self.bits == 32:
            return cur + MAX32 - prev  # validado depois pelo limite plausivel
        return None  # 64 bits nao da a volta na pratica -> foi reinicio

    def update(self, t: float, in_bytes: int, out_bytes: int) -> Optional[Rate]:
        """t = time.monotonic() da leitura. Retorna Rate ou None."""
        prev, self._prev = self._prev, (t, in_bytes, out_bytes)
        if prev is None:
            return None
        dt = t - prev[0]
        if dt <= 0:
            return None
        d_in = self._delta(in_bytes, prev[1])
        d_out = self._delta(out_bytes, prev[2])
        if d_in is None or d_out is None:
            return None
        in_bps = d_in * 8 / dt
        out_bps = d_out * 8 / dt
        if in_bps > self.max_bps or out_bps > self.max_bps:
            return None
        return Rate(in_bps, out_bps)


def clamp_percent(value: float) -> Optional[float]:
    """CPU fora de 0..100 e considerada invalida."""
    if value is None or value < 0 or value > 100:
        return None
    return float(value)
