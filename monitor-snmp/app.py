import time
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from database import Database
from snmp_collector import SNMPCollector
from alert_manager import AlertManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class MonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Sistema de Monitoramento SNMP - MikroTik")
        self.geometry("1100x800")

        self.db = Database()
        self.config = self.db.carregar_configuracao()
        self.collector = SNMPCollector(
            ip=self.config.get("ip", "192.168.18.132"),
            community=self.config.get("comunidade", "public"),
            port=self.config.get("porta", 161),
            if_index=self.config.get("interface", 1)
        )
        self.alert_mgr = AlertManager()

        self.coletando = False
        self.pausado = False
        self.thread_coleta = None

        self.time_data = []
        self.in_data = []
        self.out_data = []
        self.cpu_data = []

        self._setup_ui()

    def _setup_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_realtime = self.tabview.add("Tempo Real")
        self.tab_historico = self.tabview.add("Histórico")
        self.tab_config = self.tabview.add("Configurações")

        self._setup_tab_realtime()
        self._setup_tab_historico()
        self._setup_tab_config()

    def _setup_tab_realtime(self):
        # Topo: Controles e Cards em destaque
        frame_top = ctk.CTkFrame(self.tab_realtime, fg_color="transparent")
        frame_top.pack(fill="x", padx=10, pady=5)

        # Botões
        frame_controles = ctk.CTkFrame(frame_top)
        frame_controles.pack(side="left", padx=(0, 10))

        self.btn_iniciar = ctk.CTkButton(frame_controles, text="▶ Iniciar", command=self.iniciar_coleta, width=90)
        self.btn_iniciar.pack(side="left", padx=5, pady=5)

        self.btn_pausar = ctk.CTkButton(frame_controles, text="⏸ Pausar", command=self.pausar_coleta, state="disabled", width=90)
        self.btn_pausar.pack(side="left", padx=5, pady=5)

        self.btn_resetar = ctk.CTkButton(frame_controles, text="🔄 Resetar", command=self.resetar_dados, width=90)
        self.btn_resetar.pack(side="left", padx=5, pady=5)

        # Cards Informativos por métrica
        frame_cards = ctk.CTkFrame(frame_top, fg_color="transparent")
        frame_cards.pack(side="right", fill="x", expand=True)

        self.card_in = ctk.CTkFrame(frame_cards, fg_color="#1E293B", corner_radius=8)
        self.card_in.pack(side="left", expand=True, fill="both", padx=4)
        ctk.CTkLabel(self.card_in, text="TRAFEGO IN (DOWNLOAD)", font=("Arial", 10, "bold"), text_color="#10B981").pack(pady=(4, 0))
        self.lbl_val_in = ctk.CTkLabel(self.card_in, text="0.00 bps", font=("Arial", 16, "bold"), text_color="#34D399")
        self.lbl_val_in.pack(pady=(0, 4))

        self.card_out = ctk.CTkFrame(frame_cards, fg_color="#1E293B", corner_radius=8)
        self.card_out.pack(side="left", expand=True, fill="both", padx=4)
        ctk.CTkLabel(self.card_out, text="TRAFEGO OUT (UPLOAD)", font=("Arial", 10, "bold"), text_color="#EF4444").pack(pady=(4, 0))
        self.lbl_val_out = ctk.CTkLabel(self.card_out, text="0.00 bps", font=("Arial", 16, "bold"), text_color="#F87171")
        self.lbl_val_out.pack(pady=(0, 4))

        self.card_cpu = ctk.CTkFrame(frame_cards, fg_color="#1E293B", corner_radius=8)
        self.card_cpu.pack(side="left", expand=True, fill="both", padx=4)
        ctk.CTkLabel(self.card_cpu, text="USO DE CPU", font=("Arial", 10, "bold"), text_color="#F59E0B").pack(pady=(4, 0))
        self.lbl_val_cpu = ctk.CTkLabel(self.card_cpu, text="0 %", font=("Arial", 16, "bold"), text_color="#FBBF24")
        self.lbl_val_cpu.pack(pady=(0, 4))

        # 3 Gráficos Separados: Download, Upload e CPU
        self.fig, (self.ax_in, self.ax_out, self.ax_cpu) = plt.subplots(3, 1, figsize=(8, 6), facecolor='#0F172A')
        self.fig.tight_layout(pad=2.0)

        for ax in (self.ax_in, self.ax_out, self.ax_cpu):
            ax.set_facecolor('#1E293B')
            ax.grid(True, color='#334155', linestyle='--', linewidth=0.5, alpha=0.6)
            ax.tick_params(colors='#94A3B8', labelsize=8)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#334155')
            ax.spines['bottom'].set_color('#334155')

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.tab_realtime)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)

    def _format_bps(self, bps):
        if bps >= 1_000_000_000:
            return f"{bps / 1_000_000_000:.2f} Gbps"
        elif bps >= 1_000_000:
            return f"{bps / 1_000_000:.2f} Mbps"
        elif bps >= 1_000:
            return f"{bps / 1_000:.2f} Kbps"
        return f"{bps:.2f} bps"

    def _setup_tab_historico(self):
        frame_busca = ctk.CTkFrame(self.tab_historico)
        frame_busca.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(frame_busca, text="Início (YYYY-MM-DD HH:MM:SS):").pack(side="left", padx=5)
        self.entry_inicio = ctk.CTkEntry(frame_busca, width=150)
        self.entry_inicio.pack(side="left", padx=5)

        ctk.CTkLabel(frame_busca, text="Fim:").pack(side="left", padx=5)
        self.entry_fim = ctk.CTkEntry(frame_busca, width=150)
        self.entry_fim.pack(side="left", padx=5)

        btn_buscar = ctk.CTkButton(frame_busca, text="🔍 Buscar", command=self.carregar_historico)
        btn_buscar.pack(side="left", padx=10)

        self.fig_hist, (self.ax_hist_in, self.ax_hist_out, self.ax_hist_cpu) = plt.subplots(3, 1, figsize=(8, 6), facecolor='#0F172A')
        self.fig_hist.tight_layout(pad=2.0)

        for ax in (self.ax_hist_in, self.ax_hist_out, self.ax_hist_cpu):
            ax.set_facecolor('#1E293B')
            ax.grid(True, color='#334155', linestyle='--', linewidth=0.5)
            ax.tick_params(colors='#94A3B8', labelsize=8)

        self.canvas_hist = FigureCanvasTkAgg(self.fig_hist, master=self.tab_historico)
        self.canvas_hist.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=5)

    def _setup_tab_config(self):
        scroll = ctk.CTkScrollableFrame(self.tab_config)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(scroll, text="Parâmetros SNMP", font=("Arial", 16, "bold")).pack(anchor="w", pady=5)

        self.entry_ip = self._add_field(scroll, "IP do Roteador:", self.config.get("ip", "192.168.18.132"))
        self.entry_porta = self._add_field(scroll, "Porta SNMP:", str(self.config.get("porta", 161)))
        self.entry_comunidade = self._add_field(scroll, "Comunidade SNMP:", self.config.get("comunidade", "public"))
        self.entry_interface = self._add_field(scroll, "Índice da Interface:", str(self.config.get("interface", 1)))
        self.entry_intervalo = self._add_field(scroll, "Intervalo de Coleta (s):", str(self.config.get("intervalo", 2)))

        ctk.CTkLabel(scroll, text="Thresholds e Alertas", font=("Arial", 16, "bold")).pack(anchor="w", pady=(15, 5))

        self.entry_threshold_cpu = self._add_field(scroll, "Threshold CPU (%):", str(self.config.get("threshold_cpu", 80)))
        self.entry_threshold_traffic = self._add_field(scroll, "Threshold Tráfego (bps):", str(self.config.get("threshold_traffic", 10000000)))

        self.switch_email = ctk.CTkSwitch(scroll, text="Habilitar Alerta por E-mail")
        if self.config.get("email_enabled", False):
            self.switch_email.select()
        self.switch_email.pack(anchor="w", pady=5)

        self.entry_smtp_server = self._add_field(scroll, "Servidor SMTP:", self.config.get("smtp_server", ""))
        self.entry_smtp_port = self._add_field(scroll, "Porta SMTP:", str(self.config.get("smtp_port", 587)))
        self.entry_smtp_user = self._add_field(scroll, "Usuário SMTP:", self.config.get("smtp_user", ""))
        self.entry_smtp_pass = self._add_field(scroll, "Senha SMTP:", self.config.get("smtp_pass", ""), show="*")
        self.entry_email_dest = self._add_field(scroll, "E-mail Destinatário:", self.config.get("email_destinatario", ""))

        btn_salvar = ctk.CTkButton(scroll, text="💾 Salvar Configurações", command=self.salvar_configuracoes)
        btn_salvar.pack(pady=20)

    def _add_field(self, master, label_text, default_val, show=None):
        ctk.CTkLabel(master, text=label_text).pack(anchor="w", pady=(5, 0))
        entry = ctk.CTkEntry(master, show=show)
        entry.insert(0, default_val)
        entry.pack(fill="x", pady=(0, 5))
        return entry

    def salvar_configuracoes(self):
        try:
            self.config = {
                "ip": self.entry_ip.get().strip(),
                "porta": int(self.entry_porta.get()),
                "comunidade": self.entry_comunidade.get().strip(),
                "interface": int(self.entry_interface.get()),
                "intervalo": int(self.entry_intervalo.get()),
                "threshold_cpu": float(self.entry_threshold_cpu.get()),
                "threshold_traffic": float(self.entry_threshold_traffic.get()),
                "email_enabled": bool(self.switch_email.get()),
                "smtp_server": self.entry_smtp_server.get().strip(),
                "smtp_port": int(self.entry_smtp_port.get()),
                "smtp_user": self.entry_smtp_user.get().strip(),
                "smtp_pass": self.entry_smtp_pass.get(),
                "email_destinatario": self.entry_email_dest.get().strip()
            }
            self.db.salvar_configuracao(self.config)
            
            if self.collector:
                self.collector.atualizar_parametros(
                    ip=self.config["ip"],
                    community=self.config["comunidade"],
                    if_index=self.config["interface"]
                )
                
            messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar configurações: {e}")

    def iniciar_coleta(self):
        if not self.coletando:
            self.coletando = True
            self.pausado = False
            self.btn_iniciar.configure(state="disabled")
            self.btn_pausar.configure(state="normal", text="⏸ Pausar")
            self.thread_coleta = threading.Thread(target=self._loop_coleta, daemon=True)
            self.thread_coleta.start()

    def pausar_coleta(self):
        if self.coletando:
            self.pausado = not self.pausado
            if self.pausado:
                self.btn_pausar.configure(text="▶ Retomar")
            else:
                self.btn_pausar.configure(text="⏸ Pausar")

    def resetar_dados(self):
        self.time_data.clear()
        self.in_data.clear()
        self.out_data.clear()
        self.cpu_data.clear()
        self.lbl_val_in.configure(text="0.00 bps")
        self.lbl_val_out.configure(text="0.00 bps")
        self.lbl_val_cpu.configure(text="0 %")
        self.atualizar_grafico_realtime()

    def _loop_coleta(self):
        while self.coletando:
            if not self.pausado:
                try:
                    if self.collector:
                        self.collector.atualizar_parametros(
                            ip=self.config["ip"],
                            community=self.config["comunidade"],
                            if_index=self.config["interface"]
                        )

                    bps_in, bps_out, cpu = self.collector.coletar_metricas()
                    timestamp_now = datetime.now()
                    hora_str = timestamp_now.strftime("%H:%M:%S")

                    self.db.salvar_amostra(bps_in, bps_out, cpu, timestamp_now.strftime("%Y-%m-%d %H:%M:%S"))

                    self.time_data.append(hora_str)
                    self.in_data.append(bps_in)
                    self.out_data.append(bps_out)
                    self.cpu_data.append(cpu)

                    if len(self.time_data) > 30:
                        self.time_data.pop(0)
                        self.in_data.pop(0)
                        self.out_data.pop(0)
                        self.cpu_data.pop(0)

                    self.after(0, lambda i=bps_in, o=bps_out, c=cpu: self._atualizar_cards(i, o, c))

                    self.alert_mgr.avaliar_thresholds(
                        bps_in, bps_out, cpu, self.config,
                        callback_popup=lambda t, m: self.after(0, lambda: messagebox.showwarning(t, m))
                    )

                    self.after(0, self.atualizar_grafico_realtime)

                except Exception as e:
                    print(f"Falha na consulta SNMP: {e}")

            time.sleep(self.config.get("intervalo", 2))

    def _atualizar_cards(self, bps_in, bps_out, cpu):
        self.lbl_val_in.configure(text=self._format_bps(bps_in))
        self.lbl_val_out.configure(text=self._format_bps(bps_out))
        self.lbl_val_cpu.configure(text=f"{cpu:.1f} %")

    def atualizar_grafico_realtime(self):
        self.ax_in.clear()
        self.ax_out.clear()
        self.ax_cpu.clear()

        for ax in (self.ax_in, self.ax_out, self.ax_cpu):
            ax.set_facecolor('#1E293B')
            ax.grid(True, color='#334155', linestyle='--', linewidth=0.5, alpha=0.6)
            ax.tick_params(colors='#94A3B8', labelsize=8)

        self.ax_in.set_title("DOWNLOAD (IN)", color='#10B981', fontdict={'fontsize': 10, 'weight': 'bold'}, pad=4)
        self.ax_in.set_ylabel("bps", color='#94A3B8', fontsize=8)

        self.ax_out.set_title("UPLOAD (OUT)", color='#EF4444', fontdict={'fontsize': 10, 'weight': 'bold'}, pad=4)
        self.ax_out.set_ylabel("bps", color='#94A3B8', fontsize=8)

        self.ax_cpu.set_title("USO DE CPU (%)", color='#F59E0B', fontdict={'fontsize': 10, 'weight': 'bold'}, pad=4)
        self.ax_cpu.set_ylabel("%", color='#94A3B8', fontsize=8)

        if self.time_data:
            # Gráfico 1: Download (IN)
            self.ax_in.plot(self.time_data, self.in_data, color="#10B981", linewidth=1.8)
            self.ax_in.fill_between(self.time_data, self.in_data, color="#10B981", alpha=0.15)
            self.ax_in.tick_params(axis='x', rotation=30)

            # Gráfico 2: Upload (OUT)
            self.ax_out.plot(self.time_data, self.out_data, color="#EF4444", linewidth=1.8)
            self.ax_out.fill_between(self.time_data, self.out_data, color="#EF4444", alpha=0.15)
            self.ax_out.tick_params(axis='x', rotation=30)

            # Gráfico 3: CPU (%)
            self.ax_cpu.plot(self.time_data, self.cpu_data, color="#F59E0B", linewidth=1.8)
            self.ax_cpu.fill_between(self.time_data, self.cpu_data, color="#F59E0B", alpha=0.2)
            self.ax_cpu.set_ylim(0, 100)
            self.ax_cpu.tick_params(axis='x', rotation=30)

        self.fig.tight_layout()
        self.canvas.draw()

    def carregar_historico(self):
        inicio = self.entry_inicio.get().strip()
        fim = self.entry_fim.get().strip()

        if not inicio or not fim:
            messagebox.showwarning("Aviso", "Preencha as datas de início e fim!")
            return

        registros = self.db.buscar_historico(inicio, fim)
        if not registros:
            messagebox.showinfo("Informação", "Nenhum registro encontrado para o período informado.")
            return

        tempos = [r[4] for r in registros]
        in_b = [r[1] for r in registros]
        out_b = [r[2] for r in registros]
        cpus = [r[3] for r in registros]

        self.ax_hist_in.clear()
        self.ax_hist_out.clear()
        self.ax_hist_cpu.clear()

        for ax in (self.ax_hist_in, self.ax_hist_out, self.ax_hist_cpu):
            ax.set_facecolor('#1E293B')
            ax.grid(True, color='#334155', linestyle='--', linewidth=0.5)

        self.ax_hist_in.set_title("HISTÓRICO DOWNLOAD (IN)", color='#10B981', fontdict={'fontsize': 10, 'weight': 'bold'})
        self.ax_hist_in.plot(tempos, in_b, color="#10B981")

        self.ax_hist_out.set_title("HISTÓRICO UPLOAD (OUT)", color='#EF4444', fontdict={'fontsize': 10, 'weight': 'bold'})
        self.ax_hist_out.plot(tempos, out_b, color="#EF4444")

        self.ax_hist_cpu.set_title("HISTÓRICO CPU (%)", color='#F59E0B', fontdict={'fontsize': 10, 'weight': 'bold'})
        self.ax_hist_cpu.plot(tempos, cpus, color="#F59E0B")
        self.ax_hist_cpu.set_ylim(0, 100)

        self.fig_hist.tight_layout()
        self.canvas_hist.draw()


if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()