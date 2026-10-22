"""Cliente SNMP (pysnmp 7.x, API asyncio) com interface sincrona.

Usa um event loop proprio e persistente, para ser chamado de uma thread
de coleta sem conflitar com o loop da interface grafica.
"""
import asyncio

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData, ContextData, ObjectIdentity, ObjectType, SnmpEngine,
    UdpTransportTarget, UsmUserData, get_cmd,
    usmHMACSHAAuthProtocol, usmHMACMD5AuthProtocol,
    usmAesCfb128Protocol, usmDESPrivProtocol,
)
from pysnmp.proto.rfc1905 import NoSuchInstance, NoSuchObject, EndOfMibView

# MIBs/OIDs usados (sufixo = ifIndex)
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_HC_IN = "1.3.6.1.2.1.31.1.1.1.6"      # ifHCInOctets  (Counter64)
OID_HC_OUT = "1.3.6.1.2.1.31.1.1.1.10"    # ifHCOutOctets (Counter64)
OID_IN32 = "1.3.6.1.2.1.2.2.1.10"         # ifInOctets    (Counter32)
OID_OUT32 = "1.3.6.1.2.1.2.2.1.16"        # ifOutOctets   (Counter32)

_AUTH = {"SHA": usmHMACSHAAuthProtocol, "MD5": usmHMACMD5AuthProtocol}
_PRIV = {"AES": usmAesCfb128Protocol, "DES": usmDESPrivProtocol}


class SnmpError(Exception):
    """Falha generica de consulta SNMP."""


class SnmpTimeout(SnmpError):
    pass


class SnmpAuthError(SnmpError):
    pass


class SnmpNoSuchOid(SnmpError):
    pass


class SnmpClient:
    def __init__(self, snmp_cfg: dict):
        self.cfg = snmp_cfg
        self._loop = asyncio.new_event_loop()
        self._engine = SnmpEngine()
        self._target = None

    # ---- internos -------------------------------------------------
    def _auth_data(self):
        if str(self.cfg.get("version", "2c")) == "3":
            v3 = self.cfg["v3"]
            return UsmUserData(
                v3["user"],
                authKey=v3.get("auth_key"),
                privKey=v3.get("priv_key"),
                authProtocol=_AUTH[v3.get("auth_protocol", "SHA")],
                privProtocol=_PRIV[v3.get("priv_protocol", "AES")],
            )
        mp = 0 if str(self.cfg.get("version")) == "1" else 1
        return CommunityData(self.cfg.get("community", "public"), mpModel=mp)

    async def _get(self, oids):
        if self._target is None:
            self._target = await UdpTransportTarget.create(
                (self.cfg["host"], int(self.cfg.get("port", 161))),
                timeout=float(self.cfg.get("timeout", 2)),
                retries=int(self.cfg.get("retries", 1)),
            )
        err_ind, err_stat, err_idx, var_binds = await get_cmd(
            self._engine, self._auth_data(), self._target, ContextData(),
            *[ObjectType(ObjectIdentity(o)) for o in oids],
        )
        return err_ind, err_stat, err_idx, var_binds

    # ---- API publica ----------------------------------------------
    def get(self, oids):
        """Retorna {oid: valor}. Lanca SnmpError (ou subclasse) em falha."""
        try:
            err_ind, err_stat, err_idx, var_binds = self._loop.run_until_complete(
                asyncio.wait_for(self._get(oids), timeout=30)
            )
        except asyncio.TimeoutError as e:
            raise SnmpTimeout("tempo esgotado na consulta SNMP") from e
        except Exception as e:  # erro de rede/transporte/config
            raise SnmpError(f"erro de transporte SNMP: {e}") from e

        if err_ind:
            msg = str(err_ind)
            low = msg.lower()
            if "timeout" in low or "no snmp response" in low:
                raise SnmpTimeout(f"sem resposta do equipamento ({msg})")
            if "wrong" in low or "unknown user" in low or "authentication" in low \
                    or "decrypt" in low or "digest" in low:
                raise SnmpAuthError(f"falha de autenticacao ({msg})")
            raise SnmpError(msg)
        if err_stat:
            raise SnmpError(f"{err_stat.prettyPrint()} em {err_idx}")

        result = {}
        for name, val in var_binds:
            if isinstance(val, (NoSuchObject, NoSuchInstance, EndOfMibView)):
                raise SnmpNoSuchOid(f"OID nao suportado: {name.prettyPrint()}")
            result[str(name)] = val
        return result

    def get_ints(self, oids):
        raw = self.get(oids)
        out = {}
        for oid in oids:
            out[oid] = int(raw[oid])
        return out

    def get_text(self, oid):
        return str(self.get([oid])[oid])

    def close(self):
        try:
            pending = asyncio.all_tasks(self._loop)
            for t in pending:
                t.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
