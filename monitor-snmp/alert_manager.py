import smtplib
from email.mime.text import MIMEText
import time

class AlertManager:
    def __init__(self):
        self.last_email_time = 0
        self.email_cooldown = 300  # 5 minutos
        self.traffic_exceeded = False
        self.cpu_exceeded = False

    def enviar_email(self, config, assunto, mensagem):
        try:
            msg = MIMEText(mensagem)
            msg['Subject'] = assunto
            msg['From'] = config.get('smtp_user', '')
            msg['To'] = config.get('email_destino', '')

            server = smtplib.SMTP(config.get('smtp_host', 'smtp.gmail.com'), config.get('smtp_port', 587))
            server.starttls()
            server.login(config.get('smtp_user', ''), config.get('smtp_pass', ''))
            server.send_message(msg)
            server.quit()
            return True, "E-mail enviado com sucesso!"
        except Exception as e:
            return False, f"Falha ao enviar e-mail: {str(e)}"

    def avaliar_thresholds(self, bps_in, bps_out, cpu_usage, config, callback_popup):
        agora = time.time()
        threshold_trafego = float(config.get('threshold_trafego', 1000000))
        threshold_cpu = float(config.get('threshold_cpu', 80))
        maior_trafego = max(bps_in, bps_out)

        if maior_trafego > threshold_trafego:
            if not self.traffic_exceeded or (agora - self.last_email_time > self.email_cooldown):
                msg = f"Limite de Tráfego excedido!\nObservado: {maior_trafego/1e6:.2f} Mbps | Limite: {threshold_trafego/1e6:.2f} Mbps"
                if config.get('tipo_alerta') in ['Pop-up', 'Ambos']:
                    callback_popup("Alerta de Tráfego", msg)
                if config.get('tipo_alerta') in ['E-mail', 'Ambos']:
                    self.enviar_email(config, "[ALERTA] Tráfego de Rede Excedido", msg)
                self.traffic_exceeded = True
                self.last_email_time = agora
        else:
            self.traffic_exceeded = False

        if cpu_usage > threshold_cpu:
            if not self.cpu_exceeded or (agora - self.last_email_time > self.email_cooldown):
                msg = f"Limite de CPU excedido!\nObservado: {cpu_usage:.1f}% | Limite: {threshold_cpu:.1f}%"
                if config.get('tipo_alerta') in ['Pop-up', 'Ambos']:
                    callback_popup("Alerta de CPU", msg)
                if config.get('tipo_alerta') in ['E-mail', 'Ambos']:
                    self.enviar_email(config, "[ALERTA] Uso de CPU Excedido", msg)
                self.cpu_exceeded = True
                self.last_email_time = agora
        else:
            self.cpu_exceeded = False