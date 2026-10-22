"""Coleta IN/OUT e CPU via SNMPv1/v2c/v3 usando o cliente compartilhado."""
from app import snmp_client as sc
from app.metrics import RateCalculator, clamp_percent


class SNMPCollector:
    def __init__(self, config):
        self.update_config(config, force=True)

    def update_config(self, config, force=False):
        config = dict(config)
        signature = (config.get("ip"), config.get("porta"), config.get("comunidade"),
                     config.get("snmp_version"), config.get("v3_user"), config.get("v3_auth_key"),
                     config.get("v3_priv_key"), config.get("interface"), config.get("cpu_oid"))
        if force or signature != getattr(self, "_signature", None):
            if hasattr(self, "client"):
                self.client.close()
            version = str(config.get("snmp_version", "2c"))
            snmp = {"host": config.get("ip", "127.0.0.1"), "port": int(config.get("porta", 161)),
                    "version": version, "community": config.get("comunidade", "public"),
                    "timeout": float(config.get("timeout", 2)), "retries": 1}
            if version == "3":
                snmp["v3"] = {"user": config.get("v3_user", ""), "auth_key": config.get("v3_auth_key"),
                              "priv_key": config.get("v3_priv_key"), "auth_protocol": config.get("v3_auth_protocol", "SHA"),
                              "priv_protocol": config.get("v3_priv_protocol", "AES")}
            self.client = sc.SnmpClient(snmp)
            self._signature = signature
            self.calc = None

    def coletar_metricas(self):
        idx = int(self._signature[7])
        candidates = [(f"{sc.OID_HC_IN}.{idx}", f"{sc.OID_HC_OUT}.{idx}", 64),
                      (f"{sc.OID_IN32}.{idx}", f"{sc.OID_OUT32}.{idx}", 32)]
        last_error = None
        values = None
        bits = 64
        for oid_in, oid_out, bits in candidates:
            try:
                values = self.client.get_ints([oid_in, oid_out])
                break
            except sc.SnmpNoSuchOid as exc:
                last_error = exc
        if values is None:
            raise last_error or sc.SnmpError("Contadores de interface indisponíveis")

        cpu_oid = self._signature[8]
        try:
            cpu_raw = self.client.get_ints([cpu_oid])[cpu_oid]
        except sc.SnmpNoSuchOid:
            raise sc.SnmpNoSuchOid(f"OID de CPU não suportado: {cpu_oid}")
        cpu = clamp_percent(cpu_raw)
        if cpu is None:
            raise sc.SnmpError(f"Valor de CPU inválido: {cpu_raw}")

        if self.calc is None or self.calc.bits != bits:
            self.calc = RateCalculator(bits)
        import time
        rate = self.calc.update(time.monotonic(), values[oid_in], values[oid_out])
        return ((rate.in_bps, rate.out_bps) if rate else (None, None)) + (cpu,)

    def atualizar_parametros(self, ip, community, if_index):
        config = {"ip": ip, "comunidade": community, "interface": if_index,
                  "porta": self._signature[1], "snmp_version": "2c", "cpu_oid": self._signature[8]}
        self.update_config(config)

    def close(self):
        self.client.close()
