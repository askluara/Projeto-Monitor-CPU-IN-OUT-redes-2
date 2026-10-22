"""Avalia thresholds e despacha notificações sem repetir alertas continuamente."""
from datetime import datetime
from email.message import EmailMessage
from html import escape
import socket
import smtplib
import time


class AlertManager:
    def __init__(self, cooldown=300, clock=time.monotonic):
        self.cooldown = cooldown
        self._clock = clock
        self._last_sent = {}
        self._above = {}

    def reset(self):
        """Reavalia os thresholds/canais atualizados na próxima amostra."""
        self._last_sent.clear()
        self._above.clear()

    def _send_email(self, config, subject, body):
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = config["smtp_user"]
        message["To"] = config["email_destinatario"]
        message.set_content(body)
        message.add_alternative(self._email_html(subject, body), subtype="html")
        host = config["smtp_server"].strip()
        port = int(config["smtp_port"])
        try:
            if port == 465:
                connection = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                connection = smtplib.SMTP(host, port, timeout=10)
            with connection as server:
                if port != 465:
                    server.starttls()
                server.login(config["smtp_user"], config["smtp_pass"])
                server.send_message(message)
        except socket.gaierror as exc:
            raise ConnectionError(
                f"Não foi possível localizar o servidor SMTP '{host}'. "
                "Confira o nome do servidor e se há conexão com a internet/rede do IFBA."
            ) from exc
        except TimeoutError as exc:
            raise TimeoutError(
                f"A conexão com {host}:{port} expirou. O servidor pode estar indisponível "
                "ou a rede/firewall pode estar bloqueando essa porta. Confira o host e teste "
                "a porta 465 ou 587."
            ) from exc

    @staticmethod
    def _email_html(subject, body):
        """Monta um resumo visual em tabelas, compatível com clientes de e-mail."""
        fields = {}
        for line in body.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip().casefold()] = value.strip()

        metric = fields.get("métrica do alerta", "Teste de envio")
        is_test = metric.casefold().startswith("teste")
        primary_value = fields.get("valor do alerta", "Mensagem de teste")
        threshold = fields.get("limite do alerta", "—")
        stamp = fields.get("horário", "")
        tiles = []
        for key, label, color in (
            ("in", "TRÁFEGO IN · DOWNLOAD", "#34d399"),
            ("out", "TRÁFEGO OUT · UPLOAD", "#60a5fa"),
            ("cpu", "USO DE CPU", "#fbbf24"),
        ):
            value = fields.get(key)
            limit = fields.get(f"limite {key}")
            if value is not None:
                limit_line = f'<div style="margin-top:7px;color:#94a3b8;font-size:12px;">Limite: {escape(limit)}</div>' if limit else ""
                tiles.append(
                    '<td width="33.33%" valign="top" style="padding:5px;">'
                    '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
                    'style="background:#0b1220;border:1px solid #26364d;border-radius:10px;">'
                    '<tr><td style="padding:14px 12px;text-align:center;">'
                    f'<div style="color:#9fb0c7;font-size:10px;font-weight:bold;letter-spacing:.4px;">{label}</div>'
                    f'<div style="margin-top:9px;color:{color};font-size:20px;font-weight:bold;">{escape(value)}</div>'
                    f'{limit_line}</td></tr></table></td>'
                )
        metrics_row = "".join(tiles)
        if metrics_row:
            metrics_section = (
                '<tr><td style="padding:4px 22px 22px;"><div style="margin:0 5px 8px;color:#cbd5e1;'
                'font-size:13px;font-weight:bold;">RESUMO DA AMOSTRA</div>'
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{metrics_row}</tr></table></td></tr>'
            )
        else:
            safe_body = "<br>".join(escape(line) for line in body.splitlines())
            metrics_section = (
                '<tr><td style="padding:8px 28px 24px;"><div style="padding:16px;background:#0b1220;'
                'border-radius:9px;color:#cbd5e1;font-size:14px;line-height:1.7;">'
                f'{safe_body}</div></td></tr>'
            )
        stamp_section = (
            f'<div style="margin-top:14px;color:#94a3b8;font-size:12px;">Registrado em {escape(stamp)}</div>'
            if stamp else ""
        )
        return f'''<!doctype html>
<html lang="pt-BR"><body style="margin:0;padding:24px;background:#0b1220;font-family:Arial,Helvetica,sans-serif;color:#e5edf8;">
  <table role="presentation" align="center" width="100%" cellspacing="0" cellpadding="0" style="max-width:660px;margin:0 auto;background:#111c2e;border:1px solid #26364d;border-radius:14px;overflow:hidden;">
    <tr><td style="padding:22px 28px;background:#172235;border-bottom:1px solid #26364d;">
      <div style="font-size:11px;font-weight:bold;letter-spacing:1.2px;color:#60a5fa;">NETPULSE <span style="color:#64748b;">/ MONITORAMENTO SNMP</span></div>
      <h1 style="margin:14px 0 0;font-size:22px;line-height:1.3;color:#f8fafc;">{escape(subject)}</h1>
    </td></tr>
    <tr><td style="padding:22px 28px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1220;border-left:4px solid #f59e0b;border-radius:9px;">
        <tr><td style="padding:16px 18px;">
          <div style="font-size:11px;font-weight:bold;letter-spacing:.8px;color:#f59e0b;">{('TESTE DE E-MAIL' if is_test else 'ALERTA DE ' + escape(metric)).upper()}</div>
          <div style="margin-top:7px;font-size:28px;font-weight:bold;color:#f8fafc;">{escape(primary_value)}</div>
          <div style="margin-top:7px;color:#a9bad0;font-size:14px;">{'Resultado' if is_test else 'Limite do alerta'}: <strong style="color:#fbbf24;">{escape(threshold) if not is_test else 'Conexão SMTP concluída'}</strong></div>
          {stamp_section}
        </td></tr>
      </table>
    </td></tr>
    {metrics_section}
    <tr><td style="padding:15px 28px;border-top:1px solid #26364d;color:#71839c;font-size:11px;">Mensagem automática do NetPulse · Monitoramento de desempenho via SNMP</td></tr>
  </table>
</body></html>'''

    @staticmethod
    def _format_traffic(value):
        if value is None:
            return "Sem leitura"
        return f"{value:,.2f} bps"

    def evaluate(self, in_bps, out_bps, cpu, config, popup, error=None, now=None):
        """Notifica uma vez por transição; permite repetição após cooldown."""
        now = datetime.now().astimezone() if now is None else now
        checks = (
            ("IN", in_bps, float(config["threshold_traffic"])),
            ("OUT", out_bps, float(config["threshold_traffic"])),
            ("CPU", cpu, float(config["threshold_cpu"])),
        )
        channels = config.get("alert_type", "popup")
        sent = []
        for metric, value, threshold in checks:
            key = metric
            # O limite é considerado atingido quando o valor chega a ele.
            exceeded = value is not None and value >= threshold
            if not exceeded:
                self._above[key] = False
                continue
            current = self._clock()
            if self._above.get(key, False) and current - self._last_sent.get(key, float("-inf")) < self.cooldown:
                continue
            stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
            unit = "%" if metric == "CPU" else "bps"
            body = f"{metric}: {value:.2f} {unit}\nLimite: {threshold:.2f} {unit}\nHorário: {stamp}"
            if channels in ("popup", "both"):
                popup(f"Alerta de {metric}", body)
            if channels in ("email", "both"):
                try:
                    email_body = "\n".join((
                        f"Métrica do alerta: {metric}",
                        f"Valor do alerta: {value:.2f} {unit}",
                        f"Limite do alerta: {threshold:.2f} {unit}",
                        f"Horário: {stamp}",
                        f"IN: {self._format_traffic(in_bps)}",
                        f"Limite IN: {float(config['threshold_traffic']):,.2f} bps",
                        f"OUT: {self._format_traffic(out_bps)}",
                        f"Limite OUT: {float(config['threshold_traffic']):,.2f} bps",
                        f"CPU: {cpu:.2f}%" if cpu is not None else "CPU: Sem leitura",
                        f"Limite CPU: {float(config['threshold_cpu']):.2f}%",
                    ))
                    self._send_email(config, f"[Alerta SNMP] {metric} excedido", email_body)
                except Exception as exc:  # falha de e-mail deve ser visível e recuperável
                    if error:
                        error(f"Falha no envio de e-mail: {exc}")
            self._above[key] = True
            self._last_sent[key] = current
            sent.append(metric)
        return sent

    # API mantida para compatibilidade com o código anterior.
    def avaliar_thresholds(self, bps_in, bps_out, cpu_usage, config, callback_popup):
        normalized = dict(config)
        normalized.setdefault("threshold_traffic", config.get("threshold_trafego", 1_000_000))
        normalized.setdefault("alert_type", {"Pop-up": "popup", "E-mail": "email", "Ambos": "both"}.get(config.get("tipo_alerta"), "popup"))
        normalized.setdefault("smtp_server", config.get("smtp_host", "smtp.gmail.com"))
        normalized.setdefault("email_destinatario", config.get("email_destino", ""))
        return self.evaluate(bps_in, bps_out, cpu_usage, normalized, callback_popup)
