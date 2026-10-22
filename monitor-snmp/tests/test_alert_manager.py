import unittest
import socket
from datetime import datetime
from unittest.mock import patch

from alert_manager import AlertManager


class TestAlertManager(unittest.TestCase):
    def setUp(self):
        self.ticks = iter((0, 10, 301, 302, 303))
        self.alerts = AlertManager(cooldown=300, clock=lambda: next(self.ticks))
        self.popups = []
        self.errors = []
        self.config = {"threshold_traffic": 100, "threshold_cpu": 80, "alert_type": "popup"}
        self.now = datetime(2026, 1, 1, 12, 0)

    def test_alerta_identifica_metricas_valor_limite_e_horario(self):
        result = self.alerts.evaluate(101, 20, 90, self.config, lambda *x: self.popups.append(x), now=self.now)
        self.assertEqual(result, ["IN", "CPU"])
        self.assertEqual(len(self.popups), 2)
        self.assertIn("101.00 bps", self.popups[0][1])
        self.assertIn("100.00 bps", self.popups[0][1])
        self.assertIn("2026-01-01 12:00:00", self.popups[0][1])

    def test_suprime_repeticao_e_notifica_apos_recuperacao(self):
        callback = lambda *x: self.popups.append(x)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.alerts.evaluate(99, 0, 0, self.config, callback)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.assertEqual(len(self.popups), 2)

    def test_reenvia_apos_cooldown(self):
        callback = lambda *x: self.popups.append(x)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.assertEqual(len(self.popups), 2)

    def test_alerta_quando_valor_atinge_exatamente_o_limite(self):
        self.alerts.evaluate(0, 0, 1.0, {**self.config, "threshold_traffic": 1000, "threshold_cpu": 1},
                             lambda *x: self.popups.append(x), now=self.now)
        self.assertEqual(len(self.popups), 1)
        self.assertEqual(self.popups[0][0], "Alerta de CPU")

    def test_reset_reavalia_configuracao_salva_sem_esperar_cooldown(self):
        callback = lambda *x: self.popups.append(x)
        self.alerts.evaluate(101, 0, 0, self.config, callback)
        self.alerts.reset()
        self.alerts.evaluate(101, 0, 0, {**self.config, "alert_type": "both"}, callback)
        self.assertEqual(len(self.popups), 2)

    @patch("alert_manager.smtplib.SMTP")
    def test_envio_email_usa_starttls_e_destinatario_configurado(self, smtp):
        cfg = {"smtp_server": "smtp.example.test", "smtp_port": 587,
               "smtp_user": "monitor@example.test", "smtp_pass": "secret",
               "email_destinatario": "destino@example.test"}
        self.alerts._send_email(cfg, "Alerta", "CPU atingiu o limite")
        smtp.assert_called_once_with("smtp.example.test", 587, timeout=10)
        smtp.return_value.__enter__.return_value.starttls.assert_called_once_with()
        smtp.return_value.__enter__.return_value.login.assert_called_once_with(
            "monitor@example.test", "secret"
        )
        sent = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(sent["To"], "destino@example.test")
        self.assertEqual(sent.get_body(preferencelist=("html",)).get_content_type(), "text/html")
        self.assertIn("NETPULSE", sent.get_body(preferencelist=("html",)).get_content())

    def test_html_escapa_conteudo_dinamico(self):
        rendered = self.alerts._email_html("Alerta <CPU>", "CPU: 91%\nLimite: 80%")
        self.assertIn("Alerta &lt;CPU&gt;", rendered)
        self.assertNotIn("<CPU>", rendered)

    def test_html_destaca_as_tres_metricas_da_amostra(self):
        body = ("Métrica do alerta: CPU\nValor do alerta: 91.00 %\nLimite do alerta: 80.00 %\n"
                "Horário: agora\nIN: 120.00 bps\nLimite IN: 1,000.00 bps\n"
                "OUT: 240.00 bps\nLimite OUT: 1,000.00 bps\nCPU: 91.00%\nLimite CPU: 80.00%")
        rendered = self.alerts._email_html("Alerta SNMP", body)
        self.assertIn("TRÁFEGO IN", rendered)
        self.assertIn("120.00 bps", rendered)
        self.assertIn("TRÁFEGO OUT", rendered)
        self.assertIn("240.00 bps", rendered)
        self.assertIn("91.00%", rendered)

    @patch("alert_manager.smtplib.SMTP_SSL")
    def test_porta_465_usa_ssl_sem_starttls(self, smtp_ssl):
        cfg = {"smtp_server": "smtps.ifba.edu.br", "smtp_port": 465,
               "smtp_user": "monitor@ifba.edu.br", "smtp_pass": "secret",
               "email_destinatario": "destino@example.test"}
        self.alerts._send_email(cfg, "Teste", "Corpo")
        smtp_ssl.assert_called_once_with("smtps.ifba.edu.br", 465, timeout=10)
        smtp_ssl.return_value.__enter__.return_value.starttls.assert_not_called()
        smtp_ssl.return_value.__enter__.return_value.login.assert_called_once_with(
            "monitor@ifba.edu.br", "secret"
        )

    @patch("alert_manager.smtplib.SMTP_SSL", side_effect=socket.gaierror("name not found"))
    def test_erro_dns_exibe_orientacao_de_host(self, _smtp_ssl):
        cfg = {"smtp_server": "smtp.ifba.edu.br", "smtp_port": 465,
               "smtp_user": "monitor@ifba.edu.br", "smtp_pass": "secret",
               "email_destinatario": "destino@example.test"}
        with self.assertRaisesRegex(ConnectionError, "Confira o nome do servidor"):
            self.alerts._send_email(cfg, "Teste", "Corpo")


if __name__ == "__main__":
    unittest.main()
