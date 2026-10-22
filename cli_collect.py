"""Passo 1: coletor em linha de comando. Imprime IN, OUT (bps) e CPU (%)."""
import sys
import time

from app import snmp_client as sc
from app.config import load_config
from app.metrics import RateCalculator, clamp_percent


def fmt_bps(v):
    for unit in ("bps", "kbps", "Mbps", "Gbps"):
        if v < 1000 or unit == "Gbps":
            return f"{v:8.2f} {unit}"
        v /= 1000


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.json")
    idx = cfg["interface"]["index"]
    client = sc.SnmpClient(cfg["snmp"])

    try:
        print("Interface:", client.get_text(f"{sc.OID_IF_DESCR}.{idx}"))
    except sc.SnmpError as e:
        print("Aviso: nao li o nome da interface:", e)

    # tenta contadores de 64 bits; se nao houver, cai para 32 bits
    oid_in, oid_out, bits = f"{sc.OID_HC_IN}.{idx}", f"{sc.OID_HC_OUT}.{idx}", 64
    try:
        client.get_ints([oid_in, oid_out])
    except sc.SnmpNoSuchOid:
        oid_in, oid_out, bits = f"{sc.OID_IN32}.{idx}", f"{sc.OID_OUT32}.{idx}", 32
        print("Contadores HC indisponiveis, usando 32 bits")
    except sc.SnmpError as e:
        print("Falha inicial:", e)

    calc = RateCalculator(bits, cfg.get("max_plausible_bps", 1e10))
    cpu_oid = cfg["oids"]["cpu"]
    interval = float(cfg["collect_interval_s"])
    print(f"Coletando a cada {interval}s (Ctrl+C para sair)\n")

    try:
        while True:
            t0 = time.monotonic()
            try:
                v = client.get_ints([oid_in, oid_out, cpu_oid])
                t = time.monotonic()
                rate = calc.update(t, v[oid_in], v[oid_out])
                cpu = clamp_percent(v[cpu_oid])
                if rate is None:
                    print("IN/OUT: aguardando 2a leitura ou amostra descartada",
                          f"| CPU: {cpu}%")
                else:
                    print(f"IN {fmt_bps(rate.in_bps)} | OUT {fmt_bps(rate.out_bps)} | CPU {cpu}%")
            except sc.SnmpError as e:
                calc.reset_state()  # evita taxa gigante apos a falha
                print(f"[ERRO SNMP] {type(e).__name__}: {e}")
            time.sleep(max(0.0, interval - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
