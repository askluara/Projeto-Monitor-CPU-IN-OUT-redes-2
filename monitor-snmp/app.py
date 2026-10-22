"""Interface gráfica do monitor SNMP."""
from datetime import datetime
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from alert_manager import AlertManager
from app.history_filters import HISTORY_PERIODS, period_bounds
from app.storage import Storage
from snmp_collector import SNMPCollector


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "axes.titleweight": "semibold",
    "axes.titlesize": 12,
})


class MonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NetPulse | Monitoramento SNMP")
        self.geometry("1180x820")
        self.minsize(900, 680)
        self.configure(fg_color="#0b1220")
        self.db = Storage()
        self.config = self._load_config()
        self.collector = SNMPCollector(self.config)
        self.alerts = AlertManager()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.worker = None
        self._stopping = False
        self._session_id = 0
        self._closing = False
        self._ui_queue = queue.Queue()
        self._ui_pump_id = None
        self._active_alert_popups = {}
        self.samples = []
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _load_config(self):
        defaults = {"ip": "127.0.0.1", "porta": 161, "comunidade": "public", "snmp_version": "2c",
                    "interface": 1, "intervalo": 5, "cpu_oid": "1.3.6.1.2.1.25.3.3.1.2.1",
                    "threshold_cpu": 80, "threshold_traffic": 10000000, "alert_type": "popup",
                    "email_enabled": False, "email_destinatario": "", "smtp_server": "",
                    "smtp_port": 587, "smtp_user": "", "smtp_pass": "", "v3_user": "",
                    "v3_auth_key": "", "v3_priv_key": "", "v3_auth_protocol": "SHA", "v3_priv_protocol": "AES"}
        try:
            import json
            from pathlib import Path
            p = Path("monitor-config.json")
            if p.exists():
                defaults.update(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
        return defaults

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(12, 4))
        ctk.CTkLabel(top, text="NETPULSE", font=ctk.CTkFont(size=23, weight="bold"), text_color="#60a5fa").pack(anchor="w")
        ctk.CTkLabel(top, text="Monitoramento de desempenho do roteador via SNMP", text_color="#94a3b8").pack(anchor="w", pady=(0, 0))
        self.tabs = ctk.CTkTabview(
            self, corner_radius=14, fg_color="#101827", anchor="e",
            segmented_button_fg_color="#172235",
            segmented_button_selected_color="#2563eb",
            segmented_button_unselected_color="#172235",
        )
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(2, 10))
        self.live_tab = self.tabs.add("Tempo real")
        self.history_tab = self.tabs.add("Histórico")
        self.settings_tab = self.tabs.add("Configurações")
        self._build_live()
        self._build_history()
        self._build_settings()
        self._schedule_ui_pump()

    def _build_live(self):
        controls = ctk.CTkFrame(self.live_tab, fg_color="transparent")
        controls.pack(fill="x", padx=14, pady=12)
        self.status = ctk.CTkLabel(controls, text="● Desconectado", text_color="#94a3b8")
        self.status.pack(side="right", padx=8)
        self.start_btn = ctk.CTkButton(controls, text="▶  Iniciar coleta", command=self.start, height=38)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.pause_btn = ctk.CTkButton(controls, text="Ⅱ  Pausar", command=self.toggle_pause, state="disabled", fg_color="#334155", height=38)
        self.pause_btn.pack(side="left", padx=8)
        self.stop_btn = ctk.CTkButton(controls, text="■  Encerrar", command=self.stop_collection, state="disabled", fg_color="#7f1d1d", height=38)
        self.stop_btn.pack(side="left", padx=8)
        ctk.CTkButton(controls, text="↻  Resetar sessão", command=self.reset, fg_color="#334155", height=38).pack(side="left", padx=8)
        self.dashboard = ctk.CTkFrame(self.live_tab, fg_color="transparent")
        self.dashboard.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.metrics_panel = ctk.CTkFrame(self.dashboard, fg_color="transparent", width=232)
        self.metrics_panel.pack(side="right", fill="y", padx=(8, 2), pady=4)
        self.metrics_panel.pack_propagate(False)
        self.metric_labels = {}
        card_specs = (
            ("in", "TRÁFEGO IN · DOWNLOAD", "#34d399", "Entrada da interface"),
            ("out", "TRÁFEGO OUT · UPLOAD", "#60a5fa", "Saída da interface"),
            ("cpu", "USO DE CPU", "#fbbf24", "Dentro do limite"),
        )
        for name, title, tint, detail in card_specs:
            card = ctk.CTkFrame(self.metrics_panel, fg_color="#111c2e", corner_radius=13, height=112)
            card.pack(fill="x", padx=4, pady=6)
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=title, text_color="#94a3b8",
            font=ctk.CTkFont(size=9, weight="bold")).pack(pady=(10, 0))
            val = ctk.CTkLabel(card, text="—", text_color=tint,
                               font=ctk.CTkFont(size=19, weight="bold"))
            val.pack(pady=(0, 0))
            self.metric_labels[name] = val
            detail_label = ctk.CTkLabel(card, text=detail, text_color="#94a3b8",
                                        font=ctk.CTkFont(size=9), wraplength=198)
            detail_label.pack(pady=(0, 6))
            if name == "cpu":
                self.cpu_card = card
                self.cpu_alert_label = detail_label
        self.live_fig = plt.figure(figsize=(8, 7), facecolor="#0b1220")
        grid = self.live_fig.add_gridspec(3, 1, height_ratios=(1, 1, 1), hspace=.42)
        self.ax_in = self.live_fig.add_subplot(grid[0, 0])
        self.ax_out = self.live_fig.add_subplot(grid[1, 0])
        self.ax_cpu = self.live_fig.add_subplot(grid[2, 0])
        self.live_fig.subplots_adjust(left=.085, right=.985, top=.88, bottom=.11)
        self.live_readout = self.live_fig.text(
            .5, .965, "Passe o mouse sobre um ponto ou clique para fixar a leitura conjunta",
            ha="center", va="center", color="#cbd5e1", fontsize=10,
            bbox={"boxstyle": "round,pad=.45", "fc": "#172235", "ec": "#334155"},
        )
        self._style_axes((self.ax_in, self.ax_out, self.ax_cpu))
        self.live_canvas = FigureCanvasTkAgg(self.live_fig, master=self.dashboard)
        self.live_canvas.get_tk_widget().pack(side="left", fill="both", expand=True, padx=(2, 4), pady=4)
        self.live_canvas.mpl_connect("motion_notify_event", self._on_chart_hover)
        self.live_canvas.mpl_connect("button_press_event", self._on_chart_click)
        self._draw_live()

    def _style_axes(self, axes):
        for ax in axes:
            ax.set_facecolor("#111c2e")
            ax.grid(True, color="#25344a", linestyle="--", linewidth=.6)
            ax.tick_params(colors="#94a3b8", labelsize=9)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color("#334155")
            ax.title.set_fontfamily("sans-serif")
            ax.title.set_fontweight("semibold")

    @staticmethod
    def _set_cpu_scale(ax, values):
        values = [float(value) for value in values
                  if value is not None and math.isfinite(float(value))]
        if not values:
            ax.set_ylim(0, 10)
            return
        low, high = min(values), max(values)
        padding = max((high - low) * .2, max(abs(low), abs(high)) * .08, .5)
        lower = max(0, low - padding)
        upper = min(100, high + padding)
        if upper <= lower:
            upper = min(100, lower + 1)
        ax.set_ylim(lower, upper)

    @staticmethod
    def _plot_series(ax, times, values, label, color, unit, alert_threshold=None,
                     alert_thresholds=None):
        color_points_by_threshold = alert_threshold is not None or alert_thresholds is not None
        if alert_thresholds is None:
            alert_thresholds = [alert_threshold] * len(values)
        points = [(stamp, float(value), limit)
                  for stamp, value, limit in zip(times, values, alert_thresholds)
                  if value is not None and math.isfinite(float(value))]
        if not points:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.text(.5, .5, "Aguardando amostra válida", transform=ax.transAxes,
                    ha="center", va="center", color="#64748b", fontsize=11)
            if unit == "%":
                MonitorApp._set_cpu_scale(ax, [])
            return []
        x_values, y_values, _limits = zip(*points)
        if not color_points_by_threshold:
            ax.plot(x_values, y_values, color=color, label=label, linewidth=2.2,
                    marker="o", markersize=4.5, markeredgecolor="#0b1220", markeredgewidth=1)
        else:
            ax.plot(x_values, y_values, color=color, label=label, linewidth=2.2)
            normal = [(x, y) for x, y, limit in points if limit is not None and y < limit]
            exceeded = [(x, y) for x, y, limit in points if limit is not None and y >= limit]
            unknown = [(x, y) for x, y, limit in points if limit is None]
            for group, point_color, point_label in (
                (normal, color, "_nolegend_"),
                (exceeded, "#fb7185", "CPU acima do limite"),
                (unknown, "#94a3b8", "Limite não registrado"),
            ):
                if group:
                    px, py = zip(*group)
                    ax.scatter(px, py, color=point_color, edgecolors="#0b1220",
                               linewidths=1, s=34, zorder=4, label=point_label)
        if unit == "bps":
            ax.set_ylim(0, max(max(y_values) * 1.12, 1))
        return list(y_values)

    @staticmethod
    def _set_time_ticks(axes, rows, fmt):
        count = len(rows)
        if not count:
            return
        step = max(1, math.ceil(count / 8))
        positions = list(range(0, count, step))
        if positions[-1] != count - 1:
            positions.append(count - 1)
        labels = [datetime.fromtimestamp(rows[index][0]).strftime(fmt) for index in positions]
        for ax in axes:
            ax.set_xticks(positions)
            ax.set_xticklabels(labels, rotation=15, ha="right")

    @staticmethod
    def _render_synced_readout(fig, index, pinned=False):
        rows = getattr(fig, "_sync_rows", ())
        if not rows or index < 0 or index >= len(rows):
            return
        row = rows[index]
        stamp = datetime.fromtimestamp(row[0]).strftime("%d/%m/%Y %H:%M:%S")
        in_value = MonitorApp._bps(row[1]) if row[1] is not None else "—"
        out_value = MonitorApp._bps(row[2]) if row[2] is not None else "—"
        cpu_value = "—" if row[3] is None else f"{row[3]:.2f}%"
        suffix = "  ·  FIXADO (clique novamente para liberar)" if pinned else ""
        fig._sync_readout.set_text(
            f"{stamp}   |   IN: {in_value}   |   OUT: {out_value}   |   CPU: {cpu_value}{suffix}"
        )
        fig.canvas.draw_idle()

    def _select_synced_point(self, event, pinned=False):
        if event.inaxes is None or event.xdata is None:
            return False
        fig = event.canvas.figure
        rows = getattr(fig, "_sync_rows", ())
        axes = getattr(fig, "_sync_axes", ())
        if not rows or event.inaxes not in axes:
            return False
        index = int(round(event.xdata))
        if index < 0 or index >= len(rows) or abs(event.xdata - index) > .5:
            return False
        value_column = {axes[0]: 1, axes[1]: 2, axes[2]: 3}.get(event.inaxes)
        point_value = rows[index][value_column] if value_column is not None else None
        if point_value is None or event.y is None:
            return False
        point_y = event.inaxes.transData.transform((index, float(point_value)))[1]
        if abs(point_y - event.y) > 24:
            return False
        if pinned and getattr(fig, "_sync_pinned_index", None) == index:
            fig._sync_pinned_index = None
            for cursor in fig._sync_cursors:
                cursor.set_visible(False)
            self._render_synced_readout(fig, index, pinned=False)
            return True
        if pinned:
            fig._sync_pinned_index = index
        self._render_synced_readout(fig, index, pinned=pinned)
        for cursor in fig._sync_cursors:
            cursor.set_xdata([index, index])
            cursor.set_visible(True)
        return True

    def _on_chart_hover(self, event):
        fig = event.canvas.figure
        if getattr(fig, "_sync_pinned_index", None) is not None:
            return
        if event.inaxes is None or event.xdata is None:
            for cursor in getattr(fig, "_sync_cursors", ()):
                cursor.set_visible(False)
            readout = getattr(fig, "_sync_readout", None)
            if readout is not None:
                readout.set_text("Passe o mouse sobre um ponto ou clique para fixar a leitura conjunta")
            event.canvas.draw_idle()
            return
        if not self._select_synced_point(event):
            for cursor in getattr(fig, "_sync_cursors", ()):
                cursor.set_visible(False)
            readout = getattr(fig, "_sync_readout", None)
            if readout is not None:
                readout.set_text("Passe o mouse sobre um ponto ou clique para fixar a leitura conjunta")
            event.canvas.draw_idle()

    def _on_chart_click(self, event):
        fig = event.canvas.figure
        if getattr(fig, "_sync_pinned_index", None) is not None:
            index = fig._sync_pinned_index
            fig._sync_pinned_index = None
            for cursor in fig._sync_cursors:
                cursor.set_visible(False)
            self._render_synced_readout(fig, index, pinned=False)
            return
        self._select_synced_point(event, pinned=True)

    @staticmethod
    def _reset_sync_cursors(fig, axes, rows, readout):
        fig._sync_axes = tuple(axes)
        fig._sync_rows = list(rows)
        fig._sync_readout = readout
        fig._sync_pinned_index = None
        fig._sync_cursors = [
            ax.axvline(0, color="#e2e8f0", linestyle=":", linewidth=1, alpha=.7,
                       zorder=8, visible=False)
            for ax in axes
        ]
        readout.set_text("Passe o mouse sobre um ponto ou clique para fixar a leitura conjunta")

    @staticmethod
    def _bps(value):
        if value is None:
            return "Aguardando amostra"
        for unit in ("bps", "Kbps", "Mbps", "Gbps"):
            if value < 1000 or unit == "Gbps":
                return f"{value:,.2f} {unit}"
            value /= 1000

    def _draw_live(self):
        pinned_timestamp = None
        pinned_index = getattr(self.live_fig, "_sync_pinned_index", None)
        if pinned_index is not None:
            old_rows = getattr(self.live_fig, "_sync_rows", ())
            if 0 <= pinned_index < len(old_rows):
                pinned_timestamp = old_rows[pinned_index][0]
        for ax in (self.ax_in, self.ax_out, self.ax_cpu):
            ax.clear()
        self._style_axes((self.ax_in, self.ax_out, self.ax_cpu))
        self.ax_in.set_title("Tráfego IN · Download", loc="left", color="#e2e8f0", fontsize=12, weight="semibold")
        self.ax_out.set_title("Tráfego OUT · Upload", loc="left", color="#e2e8f0", fontsize=12, weight="semibold")
        self.ax_in.set_ylabel("bps", color="#94a3b8")
        self.ax_out.set_ylabel("bps", color="#94a3b8")
        self.ax_cpu.set_title("CPU (%) · escala adaptativa", loc="left", color="#e2e8f0", fontsize=12, weight="semibold")
        self.ax_cpu.set_ylabel("%", color="#94a3b8")
        if self.samples:
            times = list(range(len(self.samples)))
            ins, outs, cpus = ([r[i] for r in self.samples] for i in (1, 2, 3))
            self._plot_series(self.ax_in, times, ins, "IN", "#34d399", "bps")
            self._plot_series(self.ax_out, times, outs, "OUT", "#60a5fa", "bps")
            cpu_thresholds = [
                float(row[4]) if len(row) > 4 and row[4] is not None
                else float(self.config.get("threshold_cpu", 80))
                for row in self.samples
            ]
            cpu_values = self._plot_series(self.ax_cpu, times, cpus, "CPU", "#fbbf24", "%",
                                           alert_thresholds=cpu_thresholds)
            if cpu_values:
                self._set_cpu_scale(self.ax_cpu, cpu_values)
                self.ax_cpu.legend(facecolor="#111c2e", labelcolor="#e2e8f0", frameon=False, loc="upper left")
            self._set_time_ticks((self.ax_in, self.ax_out, self.ax_cpu), self.samples, "%H:%M:%S")
        else:
            self._set_cpu_scale(self.ax_cpu, [])
            for ax in (self.ax_in, self.ax_out, self.ax_cpu):
                ax.set_xticks([])
                ax.set_yticks([])
                ax.text(.5, .5, "Aguardando amostras", transform=ax.transAxes,
                        ha="center", va="center", color="#64748b", fontsize=11)
        self._reset_sync_cursors(
            self.live_fig, (self.ax_in, self.ax_out, self.ax_cpu), self.samples, self.live_readout
        )
        if pinned_timestamp is not None:
            matching = next((i for i, row in enumerate(self.samples) if row[0] == pinned_timestamp), None)
            if matching is not None:
                self.live_fig._sync_pinned_index = matching
                self._render_synced_readout(self.live_fig, matching, pinned=True)
                for cursor in self.live_fig._sync_cursors:
                    cursor.set_xdata([matching, matching])
                    cursor.set_visible(True)
        self.live_canvas.draw_idle()
    def _build_history(self):
        bar = ctk.CTkFrame(self.history_tab, fg_color="#111c2e", corner_radius=12)
        bar.pack(fill="x", padx=14, pady=14)
        ctk.CTkLabel(bar, text="Início (AAAA-MM-DD HH:MM:SS)").grid(row=0, column=0, padx=10, pady=(10, 2), sticky="w")
        ctk.CTkLabel(bar, text="Fim (AAAA-MM-DD HH:MM:SS)").grid(row=0, column=1, padx=10, pady=(10, 2), sticky="w")
        self.start_date = ctk.CTkEntry(bar, placeholder_text="2026-10-22 00:00:00", width=220)
        self.end_date = ctk.CTkEntry(bar, placeholder_text="2026-10-22 23:59:59", width=220)
        self.start_date.grid(row=1, column=0, padx=10, pady=(2, 12), sticky="ew")
        self.end_date.grid(row=1, column=1, padx=10, pady=(2, 12), sticky="ew")
        self.history_period = ctk.CTkOptionMenu(
            bar, values=["Personalizado", *HISTORY_PERIODS.keys()]
        )
        self.history_period.set("Últimas 3 horas")
        self.history_period.grid(row=1, column=2, padx=10, pady=(2, 12))
        ctk.CTkButton(bar, text="Buscar histórico", command=self.load_history).grid(row=1, column=3, padx=10)
        self.history_range = ctk.CTkLabel(self.history_tab, text="Selecione o período para consultar as amostras.", text_color="#94a3b8")
        self.history_range.pack(anchor="w", padx=20)
        self.hist_fig = plt.figure(figsize=(10, 7), facecolor="#0b1220")
        hist_grid = self.hist_fig.add_gridspec(3, 1, height_ratios=(1, 1, 1), hspace=.42)
        self.hist_in = self.hist_fig.add_subplot(hist_grid[0, 0])
        self.hist_out = self.hist_fig.add_subplot(hist_grid[1, 0])
        self.hist_cpu = self.hist_fig.add_subplot(hist_grid[2, 0])
        self.hist_fig.subplots_adjust(left=.085, right=.985, top=.88, bottom=.11)
        self.hist_readout = self.hist_fig.text(
            .5, .965, "Passe o mouse sobre um ponto ou clique para fixar a leitura conjunta",
            ha="center", va="center", color="#cbd5e1", fontsize=10,
            bbox={"boxstyle": "round,pad=.45", "fc": "#172235", "ec": "#334155"},
        )
        self._style_axes((self.hist_in, self.hist_out, self.hist_cpu))
        self.hist_canvas = FigureCanvasTkAgg(self.hist_fig, master=self.history_tab)
        self.hist_canvas.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=10)
        self.hist_canvas.mpl_connect("motion_notify_event", self._on_chart_hover)
        self.hist_canvas.mpl_connect("button_press_event", self._on_chart_click)

    def _build_settings(self):
        form = ctk.CTkScrollableFrame(self.settings_tab, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=10, pady=8)
        self.fields = {}
        groups = [("Equipamento e SNMP", [("ip", "Endereço IP / host"), ("porta", "Porta SNMP"), ("snmp_version", "Versão (1, 2c ou 3)"), ("comunidade", "Comunidade (v1/v2c)"), ("interface", "Índice da interface (ifIndex)"), ("cpu_oid", "OID da CPU")]),
                  ("Coleta e thresholds", [("intervalo", "Intervalo de coleta (segundos)"), ("threshold_traffic", "Threshold de tráfego (bps, aplicado a IN e OUT)"), ("threshold_cpu", "Threshold de CPU (%)")]),
                  ("SNMPv3", [("v3_user", "Usuário"), ("v3_auth_key", "Chave de autenticação"), ("v3_priv_key", "Chave de privacidade")]),
                  ("Alertas por e-mail", [("email_destinatario", "E-mail de destino"), ("smtp_server", "Servidor SMTP"), ("smtp_port", "Porta SMTP"), ("smtp_user", "Usuário SMTP"), ("smtp_pass", "Senha SMTP")])]
        for title, fields in groups:
            ctk.CTkLabel(form, text=title, font=ctk.CTkFont(size=17, weight="bold"), text_color="#60a5fa").pack(anchor="w", pady=(12, 4))
            for key, label in fields:
                ctk.CTkLabel(form, text=label, text_color="#cbd5e1").pack(anchor="w", pady=(5, 1))
                entry = ctk.CTkEntry(form, show="•" if key in ("smtp_pass", "v3_auth_key", "v3_priv_key") else None)
                entry.insert(0, str(self.config.get(key, "")))
                entry.pack(fill="x", pady=(0, 2))
                self.fields[key] = entry
        ctk.CTkLabel(form, text="Canal de alerta").pack(anchor="w", pady=(8, 2))
        ctk.CTkLabel(
            form,
            text=("Escolha Ambos para exibir o pop-up e enviar cada alerta por e-mail. "
                  "IFBA/Google Workspace: smtp.gmail.com, porta 465 (SSL) ou 587 (STARTTLS). "
                  "Pode ser necessária uma senha de app."),
            text_color="#94a3b8", wraplength=760, justify="left"
        ).pack(anchor="w", pady=(0, 6))
        self.alert_choice = ctk.CTkOptionMenu(form, values=["Pop-up", "E-mail", "Ambos"])
        self.alert_choice.set({"popup": "Pop-up", "email": "E-mail", "both": "Ambos"}.get(self.config.get("alert_type", "popup"), "Pop-up"))
        self.alert_choice.pack(anchor="w")
        ctk.CTkButton(form, text="Testar envio de e-mail", command=self.test_email,
                      fg_color="#334155", height=36).pack(anchor="w", pady=(10, 2))
        ctk.CTkButton(form, text="Salvar configurações", command=self.save_settings, height=40).pack(anchor="w", pady=18)

    def _email_config_from_form(self):
        cfg = dict(self.config)
        for key in ("email_destinatario", "smtp_server", "smtp_port", "smtp_user", "smtp_pass"):
            cfg[key] = self.fields[key].get().strip()
        cfg["smtp_port"] = int(cfg["smtp_port"])
        if not __import__("re").fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cfg["email_destinatario"]):
            raise ValueError("Informe um endereço de e-mail de destino válido.")
        if not all(cfg[key] for key in ("smtp_server", "smtp_user", "smtp_pass")):
            raise ValueError("Preencha o servidor, usuário e senha SMTP.")
        return cfg

    def test_email(self):
        try:
            cfg = self._email_config_from_form()
        except (ValueError, KeyError) as exc:
            self._show_alert_popup("Configuração de e-mail", str(exc), success=False)
            return

        def send_test():
            try:
                latest = self.samples[-1] if self.samples else None
                stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
                in_value = self._bps(latest[1]) if latest and latest[1] is not None else "Sem leitura"
                out_value = self._bps(latest[2]) if latest and latest[2] is not None else "Sem leitura"
                cpu_value = f"{latest[3]:.2f}%" if latest and latest[3] is not None else "Sem leitura"
                cpu_limit = (float(latest[4]) if latest and len(latest) > 4 and latest[4] is not None
                             else float(cfg.get("threshold_cpu", 80)))
                test_body = "\n".join((
                    "Métrica do alerta: Teste de e-mail",
                    "Valor do alerta: Configuração SMTP validada",
                    "Limite do alerta: Não se aplica",
                    f"Horário: {stamp}",
                    f"IN: {in_value}",
                    f"Limite IN: {float(cfg.get('threshold_traffic', 1_000_000)):,.2f} bps",
                    f"OUT: {out_value}",
                    f"Limite OUT: {float(cfg.get('threshold_traffic', 1_000_000)):,.2f} bps",
                    f"CPU: {cpu_value}",
                    f"Limite CPU: {cpu_limit:.2f}%",
                ))
                self.alerts._send_email(
                    cfg,
                    "[Teste] Monitoramento SNMP",
                    test_body,
                )
            except Exception as exc:
                self._ui_queue.put(("email_test", False, str(exc)))
            else:
                self._ui_queue.put(("email_test", True, "E-mail de teste enviado com sucesso."))

        threading.Thread(target=send_test, daemon=True).start()

    def save_settings(self):
        try:
            cfg = dict(self.config)
            for key, widget in self.fields.items():
                cfg[key] = widget.get().strip()
            cfg["porta"] = int(cfg["porta"])
            cfg["interface"] = int(cfg["interface"])
            cfg["intervalo"] = float(cfg["intervalo"])
            cfg["threshold_traffic"] = float(cfg["threshold_traffic"])
            cfg["threshold_cpu"] = float(cfg["threshold_cpu"])
            cfg["smtp_port"] = int(cfg["smtp_port"])
            if not cfg["ip"] or not (1 <= cfg["porta"] <= 65535) or cfg["interface"] < 1:
                raise ValueError("Informe host, porta (1–65535) e índice de interface válido.")
            if cfg["intervalo"] <= 0 or cfg["threshold_traffic"] < 0 or not (0 <= cfg["threshold_cpu"] <= 100):
                raise ValueError("Intervalo deve ser positivo; tráfego não negativo; CPU entre 0 e 100%.")
            cfg["snmp_version"] = cfg["snmp_version"].lower()
            if cfg["snmp_version"] not in ("1", "2c", "3"):
                raise ValueError("Versão SNMP deve ser 1, 2c ou 3.")
            cfg["alert_type"] = {"Pop-up": "popup", "E-mail": "email", "Ambos": "both"}[self.alert_choice.get()]
            cfg["email_enabled"] = cfg["alert_type"] in ("email", "both")
            if cfg["email_enabled"]:
                if not __import__("re").fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cfg["email_destinatario"]):
                    raise ValueError("Informe um endereço de e-mail de destino válido.")
                if not all(cfg[k] for k in ("smtp_server", "smtp_user", "smtp_pass")):
                    raise ValueError("Preencha servidor, usuário e senha SMTP para habilitar o e-mail.")
            if cfg["snmp_version"] == "3" and not cfg["v3_user"]:
                raise ValueError("Informe o usuário SNMPv3.")
            import json
            from pathlib import Path
            Path("monitor-config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self.config = cfg
            self.alerts.reset()
            self.collector.update_config(cfg)
            if self.worker and self.worker.is_alive() and self.pause_event.is_set():
                messagebox.showinfo(
                    "Configurações",
                    "Parâmetros salvos. A coleta está pausada; clique em Retomar para aplicar os novos limites e canais de alerta."
                )
            else:
                messagebox.showinfo(
                    "Configurações",
                    "Parâmetros salvos. Os novos valores serão usados na próxima coleta, sem reiniciar a aplicação."
                )
        except (ValueError, OSError) as exc:
            messagebox.showerror("Configuração inválida", str(exc))

    def start(self):
        if self.worker and self.worker.is_alive():
            if self._stopping:
                return
            if self.pause_event.is_set():
                self.pause_event.clear()
                self.pause_btn.configure(text="Ⅱ  Pausar")
                self.status.configure(text="● Coletando", text_color="#34d399")
            return
        self._stopping = False
        self.stop_event.clear()
        self.pause_event.clear()
        self.worker = threading.Thread(target=self._collect_loop, daemon=True)
        self.worker.start()
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.status.configure(text="● Coletando", text_color="#34d399")

    def toggle_pause(self):
        if not self.worker or not self.worker.is_alive() or self._stopping:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.configure(text="Ⅱ  Pausar")
            self.status.configure(text="● Coletando", text_color="#34d399")
        else:
            self.pause_event.set()
            self.pause_btn.configure(text="▶  Retomar")
            self.status.configure(text="Ⅱ Pausado", text_color="#fbbf24")

    def reset(self):
        # Ignora callbacks de amostras que estavam em trânsito quando o usuário
        # resetou; a próxima consulta começa a nova série exibida.
        self._session_id += 1
        self.samples.clear()
        self.metric_labels["in"].configure(text="—")
        self.metric_labels["out"].configure(text="—")
        self.metric_labels["cpu"].configure(text="—")
        self._set_cpu_alert(False)
        self._draw_live()

    def stop_collection(self):
        if not self.worker or not self.worker.is_alive() or self._stopping:
            return
        self._stopping = True
        self.pause_event.clear()
        self.stop_event.set()
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="Encerrando coleta…", text_color="#fbbf24")

    def _collect_loop(self):
        while not self.stop_event.is_set():
            if self.pause_event.is_set():
                self.stop_event.wait(.2)
                continue
            started = time.monotonic()
            session_id = self._session_id
            sample_config = dict(self.config)
            try:
                in_bps, out_bps, cpu = self.collector.coletar_metricas()
                ts = time.time()
                cpu_threshold = float(sample_config.get("threshold_cpu", 80))
                sample_row = (ts, in_bps, out_bps, cpu, cpu_threshold)
                self.db.add_sample(in_bps, out_bps, cpu, ts, cpu_threshold)
                self._ui_queue.put(("sample", sample_row, session_id))
                notified = self.alerts.evaluate(in_bps, out_bps, cpu, sample_config,
                                                lambda title, msg: self._ui_queue.put(("popup", title, msg)),
                                                lambda msg: self._ui_queue.put(("status", f"⚠ {msg}", "#f87171")))
                values = {"IN": (in_bps, sample_config["threshold_traffic"]),
                          "OUT": (out_bps, sample_config["threshold_traffic"]),
                          "CPU": (cpu, cpu_threshold)}
                for metric in notified:
                    value, threshold = values[metric]
                    unit = "%" if metric == "CPU" else "bps"
                    stamp = datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
                    body = f"{metric}: {value:.2f} {unit}; limite {threshold:.2f} {unit}; {stamp}"
                    self.db.add_alert_event(metric.lower(), value, threshold, sample_config["alert_type"], body, ts)
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.db.add_error(type(exc).__name__, str(exc))
                    self._ui_queue.put(("status", f"⚠ Falha SNMP: {exc}", "#f87171"))
            delay = max(0, float(self.config.get("intervalo", 5)) - (time.monotonic() - started))
            self.stop_event.wait(delay)
        self._ui_queue.put(("stopped",))

    def _schedule_ui_pump(self):
        if not self._closing:
            self._ui_pump_id = self.after(100, self._process_ui_events)

    def _process_ui_events(self):
        self._ui_pump_id = None
        while True:
            try:
                event = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "sample":
                self._on_sample(event[1], event[2])
            elif kind == "status":
                self.status.configure(text=event[1], text_color=event[2])
            elif kind == "popup":
                self._show_alert_popup(event[1], event[2])
            elif kind == "email_test":
                self._show_alert_popup(
                    "Teste de e-mail" if event[1] else "Falha no teste de e-mail",
                    event[2], success=event[1]
                )
            elif kind == "stopped":
                self._stopped()
        self._schedule_ui_pump()

    def _show_alert_popup(self, title, message, success=False):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("460x270")
        dialog.resizable(False, False)
        dialog.configure(fg_color="#0b1220")
        dialog.transient(self)
        dialog.attributes("-topmost", True)
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - 460) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - 270) // 2)
        dialog.geometry(f"460x270+{x}+{y}")

        accent = "#34d399" if success else "#f59e0b"
        panel = ctk.CTkFrame(dialog, fg_color="#111c2e", corner_radius=14)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkFrame(panel, width=5, fg_color=accent, corner_radius=3).pack(side="left", fill="y", padx=(14, 12), pady=16)
        content = ctk.CTkFrame(panel, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=(0, 14), pady=14)
        content.configure(width=350, height=210)
        content.pack_propagate(False)
        ctk.CTkLabel(content, text="NOTIFICAÇÃO DO MONITOR", text_color=accent,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", pady=(4, 3))
        ctk.CTkLabel(content, text=title, text_color="#f8fafc",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 12))
        lines = message.splitlines()
        value_label = None
        if lines:
            value_label = ctk.CTkLabel(content, text=lines[0], text_color="#e2e8f0",
                                       font=ctk.CTkFont(size=15, weight="bold"),
                                       width=350, wraplength=340, anchor="w", justify="left")
            value_label.pack(anchor="w", pady=(0, 5))
        details = "\n".join(lines[1:])
        ctk.CTkLabel(content, text=details, text_color="#cbd5e1",
                     font=ctk.CTkFont(size=12), width=350, height=68,
                     wraplength=340, anchor="nw", justify="left").pack(anchor="w", pady=2)
        ctk.CTkButton(content, text="Entendi", command=dialog.destroy, width=110,
                      height=34, fg_color=accent, text_color="#0b1220",
                      hover_color="#10b981" if success else "#d97706").pack(anchor="e", pady=(14, 0))
        dialog.bind("<Return>", lambda _event: dialog.destroy())
        metric_name = title.removeprefix("Alerta de ").strip().upper()
        if metric_name in ("CPU", "IN", "OUT") and value_label is not None:
            self._active_alert_popups[metric_name] = (dialog, value_label)
        dialog.grab_set()

    def _update_open_alert_value(self, metric, value):
        active = self._active_alert_popups.get(metric)
        if not active:
            return
        dialog, label = active
        try:
            if not dialog.winfo_exists():
                self._active_alert_popups.pop(metric, None)
                return
            unit = "%" if metric == "CPU" else "bps"
            label.configure(text=f"{metric}: {value:.2f} {unit}")
        except tk.TclError:
            self._active_alert_popups.pop(metric, None)

    def _set_cpu_alert(self, active, value=None, threshold=None):
        if threshold is None:
            threshold = float(self.config.get("threshold_cpu", 80))
        if value is None:
            value = 0.0
        if active:
            self.cpu_card.configure(fg_color="#451a1a")
            self.cpu_alert_label.configure(
                text=f"ALERTA ATIVO · {value:.1f}% / limite {threshold:.1f}%",
                text_color="#fecaca",
                font=ctk.CTkFont(size=11, weight="bold"),
            )
            self.metric_labels["cpu"].configure(text_color="#f87171")
        else:
            self.cpu_card.configure(fg_color="#111c2e")
            self.cpu_alert_label.configure(
                text=f"Dentro do limite · {threshold:.1f}%",
                text_color="#94a3b8",
                font=ctk.CTkFont(size=11),
            )
            self.metric_labels["cpu"].configure(text_color="#fbbf24")

    def _on_sample(self, row, session_id=None):
        if session_id is not None and session_id != self._session_id:
            return
        self.samples.append(row)
        self.samples = self.samples[-60:]
        self.metric_labels["in"].configure(text=self._bps(row[1]))
        self.metric_labels["out"].configure(text=self._bps(row[2]))
        self.metric_labels["cpu"].configure(text="—" if row[3] is None else f"{row[3]:.1f}%")
        threshold = (float(row[4]) if len(row) > 4 and row[4] is not None
                     else float(self.config.get("threshold_cpu", 80)))
        self._set_cpu_alert(row[3] is not None and row[3] >= threshold,
                            row[3] if row[3] is not None else 0, threshold)
        if row[3] is not None:
            self._update_open_alert_value("CPU", row[3])
        self._draw_live()

    def _stopped(self):
        self._stopping = False
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="● Desconectado", text_color="#94a3b8")

    def load_history(self):
        try:
            period = self.history_period.get()
            if period != "Personalizado":
                start, end = period_bounds(period)
                self.start_date.delete(0, "end")
                self.start_date.insert(0, datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S"))
                self.end_date.delete(0, "end")
                self.end_date.insert(0, datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M:%S"))
            else:
                start = datetime.strptime(self.start_date.get().strip(), "%Y-%m-%d %H:%M:%S").timestamp()
                end = datetime.strptime(self.end_date.get().strip(), "%Y-%m-%d %H:%M:%S").timestamp()
            if start > end:
                raise ValueError("O início do período deve preceder o fim.")
            rows = self.db.query_samples(start, end)
            alerts = self.db.query_alert_events(start=start, end=end, limit=1000)
            self.history_range.configure(text=f"Período: {datetime.fromtimestamp(start):%d/%m/%Y %H:%M:%S} até {datetime.fromtimestamp(end):%d/%m/%Y %H:%M:%S} · {len(rows)} amostras · {len(alerts)} alertas registrados")
            for ax in (self.hist_in, self.hist_out, self.hist_cpu):
                ax.clear()
            self._style_axes((self.hist_in, self.hist_out, self.hist_cpu))
            self.hist_in.set_title("Tráfego IN · Download", loc="left", color="#e2e8f0")
            self.hist_out.set_title("Tráfego OUT · Upload", loc="left", color="#e2e8f0")
            self.hist_in.set_ylabel("bps", color="#94a3b8")
            self.hist_out.set_ylabel("bps", color="#94a3b8")
            self.hist_cpu.set_title("CPU (%) · escala adaptativa", loc="left", color="#e2e8f0", fontsize=12, weight="semibold")
            self.hist_cpu.set_ylabel("%", color="#94a3b8")
            axes = {"in": self.hist_in, "out": self.hist_out, "cpu": self.hist_cpu}
            colors = {"in": "#34d399", "out": "#60a5fa", "cpu": "#fbbf24"}
            if rows:
                x = list(range(len(rows)))
                cpu_thresholds = [
                    float(r[4]) if len(r) > 4 and r[4] is not None else None
                    for r in rows
                ]
                for axis, col, label, color in ((self.hist_in, 1, "IN", colors["in"]),
                                                (self.hist_out, 2, "OUT", colors["out"]),
                                                (self.hist_cpu, 3, "CPU", colors["cpu"])):
                    values = self._plot_series(
                        axis, x, [r[col] for r in rows], label, color,
                        "%" if col == 3 else "bps",
                        alert_thresholds=cpu_thresholds if col == 3 else None,
                    )
                    if values:
                        handles, labels = axis.get_legend_handles_labels()
                        unique = dict(zip(labels, handles))
                        axis.legend(unique.values(), unique.keys(), facecolor="#111c2e",
                                    labelcolor="#e2e8f0", frameon=False)
                    if col == 3 and values:
                        self._set_cpu_scale(axis, values)
                self._set_time_ticks((self.hist_in, self.hist_out, self.hist_cpu), rows,
                                     "%d/%m %H:%M:%S")
            else:
                for axis in (self.hist_in, self.hist_out, self.hist_cpu):
                    axis.set_xticks([])
                    axis.set_yticks([])
                    axis.text(.5, .5, "Nenhuma amostra neste período", transform=axis.transAxes,
                              ha="center", va="center", color="#64748b", fontsize=11)
            alert_legend_added = set()
            threshold_lines_added = set()
            for ts, metric, value, threshold, _channels, _message in alerts:
                axis = axes.get(metric.lower())
                if axis and rows:
                    alert_index = min(range(len(rows)), key=lambda i: abs(rows[i][0] - ts))
                    label = "Alerta registrado" if metric not in alert_legend_added else "_nolegend_"
                    alert_legend_added.add(metric)
                    axis.scatter([alert_index], [value], color="#fb7185", edgecolors="white", linewidths=.7,
                                 s=55, zorder=5, label=label)
                    threshold_key = (metric, threshold)
                    if threshold_key not in threshold_lines_added:
                        axis.axhline(threshold, color="#fb7185", linestyle="--", linewidth=1, alpha=.65)
                        threshold_lines_added.add(threshold_key)
                    handles, labels = axis.get_legend_handles_labels()
                    unique = dict(zip(labels, handles))
                    axis.legend(unique.values(), unique.keys(), facecolor="#111c2e",
                                labelcolor="#e2e8f0", frameon=False)
            self._reset_sync_cursors(
                self.hist_fig, (self.hist_in, self.hist_out, self.hist_cpu), rows, self.hist_readout
            )
            self.hist_canvas.draw_idle()
        except ValueError as exc:
            messagebox.showerror("Período inválido", f"Use AAAA-MM-DD HH:MM:SS. {exc}")
    def _close(self):
        if self._closing:
            return
        self._closing = True
        self.stop_event.set()
        self.pause_event.clear()
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="Encerrando com segurança…", text_color="#fbbf24")
        self._wait_for_worker()

    def _wait_for_worker(self):
        if self.worker and self.worker.is_alive():
            self.after(50, self._wait_for_worker)
            return
        # CustomTkinter agenda loops de aparência e escala DPI com after().
        # Cancele os callbacks pendentes antes de destruir o interpretador Tcl,
        # inclusive os que pertencem à biblioteca.
        try:
            pending_after_ids = self.tk.splitlist(self.tk.call("after", "info"))
            for after_id in pending_after_ids:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        self._ui_pump_id = None
        self.collector.close()
        self.db.close()
        self.destroy()


if __name__ == "__main__":
    MonitorApp().mainloop()
