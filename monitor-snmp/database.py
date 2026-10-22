import sqlite3
import json

class Database:
    def __init__(self, db_name="monitor.db"):
        self.db_name = db_name
        self.criar_tabelas()

    def conectar(self):
        return sqlite3.connect(self.db_name)

    def criar_tabelas(self):
        with self.conectar() as conn:
            cursor = conn.cursor()
            
            # Tabela de leituras históricas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metricas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bps_in REAL,
                    bps_out REAL,
                    cpu REAL,
                    timestamp TEXT
                )
            """)

            # Tabela para guardar a configuração
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuracoes (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    dados TEXT
                )
            """)
            conn.commit()

    def salvar_configuracao(self, config_dict):
        with self.conectar() as conn:
            cursor = conn.cursor()
            dados_json = json.dumps(config_dict)
            cursor.execute("""
                INSERT INTO configuracoes (id, dados) 
                VALUES (1, ?) 
                ON CONFLICT(id) DO UPDATE SET dados = excluded.dados
            """, (dados_json,))
            conn.commit()

    def carregar_configuracao(self):
        config_padrao = {
            "ip": "192.168.18.132",
            "porta": 161,
            "comunidade": "public",
            "interface": 1,
            "intervalo": 2,
            "threshold_cpu": 80.0,
            "threshold_traffic": 10000000.0,
            "email_enabled": False,
            "smtp_server": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
            "email_destinatario": ""
        }

        try:
            with self.conectar() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT dados FROM configuracoes WHERE id = 1")
                row = cursor.fetchone()
                if row and row[0]:
                    config_salva = json.loads(row[0])
                    # Atualiza padrões caso falte alguma chave
                    config_padrao.update(config_salva)
                    return config_padrao
        except Exception as e:
            print(f"Erro ao carregar configuração do banco: {e}")

        return config_padrao

    def salvar_amostra(self, bps_in, bps_out, cpu, timestamp):
        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO metricas (bps_in, bps_out, cpu, timestamp)
                VALUES (?, ?, ?, ?)
            """, (bps_in, bps_out, cpu, timestamp))
            conn.commit()

    def buscar_historico(self, inicio, fim):
        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, bps_in, bps_out, cpu, timestamp 
                FROM metricas 
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            """, (inicio, fim))
            return cursor.fetchall()