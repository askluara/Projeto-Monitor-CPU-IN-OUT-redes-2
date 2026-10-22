import asyncio
import time
from pysnmp.hlapi.v3arch.asyncio import (
    get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity
)

class SNMPCollector:
    def __init__(self, ip="192.168.18.132", community="public", port=161, if_index=1):
        self.ip = str(ip).strip()
        self.community = community
        self.port = int(port)
        self.if_index = if_index

        self.oid_in_octets = f"1.3.6.1.2.1.2.2.1.10.{if_index}"   # ifInOctets
        self.oid_out_octets = f"1.3.6.1.2.1.2.2.1.16.{if_index}" # ifOutOctets
        
        # OIDs de CPU (MikroTik Propriethary e MIB-2 Standard)
        self.oid_cpu_mikrotik = "1.3.6.1.4.1.14988.1.1.1.3.1.0"
        self.oid_cpu_standard = "1.3.6.1.2.1.25.3.3.1.2.1"

        self.last_bytes_in = None
        self.last_bytes_out = None
        self.last_time = None

    def atualizar_parametros(self, ip, community, if_index):
        self.ip = str(ip).strip()
        self.community = community
        self.if_index = if_index
        self.oid_in_octets = f"1.3.6.1.2.1.2.2.1.10.{if_index}"
        self.oid_out_octets = f"1.3.6.1.2.1.2.2.1.16.{if_index}"

    async def _snmp_get_async(self, oid):
        snmp_engine = SnmpEngine()
        
        transport = await UdpTransportTarget.create(
            (self.ip, self.port),
            timeout=2.0,
            retries=1
        )
        
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmp_engine,
            CommunityData(self.community, mpModel=1), # v2c
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )

        if errorIndication:
            raise Exception(f"Erro de Conexão SNMP ({self.ip}): {errorIndication}")
        elif errorStatus:
            raise Exception(f"Erro SNMP: {errorStatus.prettyPrint()}")

        for varBind in varBinds:
            val = varBind[1]
            if hasattr(val, 'prettyPrint'):
                val_str = val.prettyPrint()
            else:
                val_str = str(val)
                
            # Trata respostas de OIDs inexistentes sem derrubar a aplicação
            if any(msg in val_str for msg in ["No Such Instance", "No Such Object", "NoSuchObject"]):
                return None
                
            return int(val_str)

    def _snmp_get(self, oid):
        return asyncio.run(self._snmp_get_async(oid))

    def coletar_metricas(self):
        now = time.time()
        
        current_in = self._snmp_get(self.oid_in_octets) or 0
        current_out = self._snmp_get(self.oid_out_octets) or 0
        
        # Tenta a OID de CPU MikroTik, se falhar tenta a OID Standard, senão retorna 0
        cpu = self._snmp_get(self.oid_cpu_mikrotik)
        if cpu is None:
            cpu = self._snmp_get(self.oid_cpu_standard)
        if cpu is None:
            cpu = 0.0

        bps_in, bps_out = 0.0, 0.0

        if self.last_bytes_in is not None and self.last_time is not None:
            time_diff = now - self.last_time
            if time_diff > 0:
                diff_in = current_in - self.last_bytes_in
                diff_out = current_out - self.last_bytes_out

                # Trata estouro de contador de 32 bits (Counter32)
                if diff_in < 0:
                    diff_in += 2**32
                if diff_out < 0:
                    diff_out += 2**32

                bps_in = (diff_in * 8) / time_diff
                bps_out = (diff_out * 8) / time_diff

        self.last_bytes_in = current_in
        self.last_bytes_out = current_out
        self.last_time = now

        return max(0.0, bps_in), max(0.0, bps_out), float(cpu)