# NetPulse — Monitoramento de roteador via SNMP

Aplicação desktop para acompanhar tráfego de entrada/saída de uma interface e uso de CPU, consultar histórico persistido e emitir alertas por pop-up e/ou e-mail. O projeto atende ao roteiro de monitoramento de Projeto e Administração de Redes. A interface foi feita em CustomTkinter e Matplotlib; coleta com PySNMP; persistência local com SQLite.

## Requisitos

- Python 3.10 ou superior.
- Um equipamento ou simulador autorizado com SNMP habilitado, endereço acessível e índice `ifIndex` conhecido.
- SNMPv1/v2c com comunidade somente leitura ou SNMPv3 com usuário configurado no equipamento. Restrinja a origem permitida no agente SNMP.
- Para alertas por e-mail, servidor SMTP acessível e credenciais válidas. A porta 465 usa SSL; outras portas usam STARTTLS.

## Instalação e execução

No terminal, na pasta raiz do repositório:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py monitor-snmp\app.py
```

No Linux/macOS, ative `.venv` com `source .venv/bin/activate` e rode `python monitor-snmp/app.py`.

### Abrir no Windows

Abra o PowerShell na pasta do projeto (`C:\Users\luara\Documents\monitor-snmp`) e rode:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py monitor-snmp\app.py
```

Se o PowerShell bloquear a ativação do ambiente virtual, abra um terminal novo e use o Python pelo caminho, sem ativar:

```powershell
py -m pip install -r requirements.txt
py monitor-snmp\app.py
```

Também dá para abrir a pasta no VS Code e executar `py monitor-snmp\app.py` no terminal integrado. A janela **NetPulse** deve abrir; vá à aba **Configurações** para informar o equipamento e depois à aba **Tempo real** para iniciar.

O banco `monitor.db` e o arquivo de configuração `monitor-config.json` são criados na pasta de execução. Ambos ficam fora do Git (`*.db` e `monitor-config.json` estão ignorados), para evitar publicar dados e segredos.

## Configuração

Na aba **Configurações**, preencha host, porta, versão SNMP, comunidade (v1/v2c), `ifIndex`, OID da CPU, intervalo e limites. A versão v3 usa usuário e chaves de autenticação/privacidade. O OID de CPU padrão é `HOST-RESOURCES-MIB::hrProcessorLoad.1` (`1.3.6.1.2.1.25.3.3.1.2.1`); ajuste-o conforme o agente e a MIB do equipamento. Para MikroTik, configure o OID de CPU que o RouterOS expõe no seu modelo/versão.

Escolha **Pop-up**, **E-mail** ou **Ambos**. O limite de tráfego é aplicado separadamente a IN e OUT: qualquer uma das séries que atingir ou exceder o limite gera alerta. Para receber também por e-mail, configure destino, host, porta, usuário e senha SMTP, selecione **Ambos** e use **Testar envio de e-mail** antes da coleta. O IFBA migrou as contas institucionais para Google Workspace e informa que o envio pelo Zimbra foi desativado; para conta IFBA no Workspace, tente `smtp.gmail.com`, porta `465` (SSL) ou `587` (STARTTLS), com o e-mail institucional como usuário. O Google exige senha de app para autenticação SMTP em contas Workspace, quando habilitada pela política da instituição. Confirme com o suporte do IFBA se SMTP externo/senha de app está permitido para sua conta. O botão de teste envia uma mensagem imediatamente e não exige iniciar a coleta. Erro de DNS indica que o host não foi encontrado; timeout indica que a conexão não completou, muitas vezes por host incorreto ou porta bloqueada na rede/firewall. As credenciais ficam no arquivo local em texto simples; não compartilhe esse arquivo nem o adicione ao repositório.

## Testar com o roteador da aula

O teste é direto se o roteador estiver configurado para permitir consultas SNMP do seu computador.  Para isso é preciso consultar o equipamento e para obter estes dados:

1. Endereço IP de gerenciamento e porta SNMP (normalmente `161`/UDP).
2. Versão habilitada (`v2c` ou `v3`); para v2c, a comunidade de leitura. Para v3, usuário e método/chaves de autenticação e privacidade.
3. Índice (`ifIndex`) da interface que será monitorada.
4. OID de CPU que o modelo/firmware disponibiliza.
5. Se o acesso é permitido a partir da rede do laboratório e se há ACL/firewall autorizando o IP do seu computador.

Na aba **Configurações**, preencha esses parâmetros. Para um laboratório v2c, selecione `2c`, informe a comunidade fornecida, o IP/porta, o `ifIndex` e um OID de CPU compatível. O padrão de CPU usa `hrProcessorLoad.1`; alguns roteadores não oferecem essa MIB, então será necessário usar o OID indicado pelo docente/fabricante. Salve. Na aba **Tempo real**, inicie a coleta e aguarde pelo menos duas consultas: a primeira leitura dos contadores só estabelece a referência, então as taxas IN/OUT aparecem a partir da seguinte.

Se houver `snmpwalk` instalado (Net-SNMP), use-o antes da demonstração para descobrir as interfaces:

```text
snmpwalk -v2c -c SUA_COMUNIDADE IP_DO_ROTEADOR 1.3.6.1.2.1.2.2.1.2
```

Cada resposta termina com o índice da interface; por exemplo, `.1.3` indica `ifIndex 3`. Use esse número no campo **Índice da interface**. Para verificar a CPU HOST-RESOURCES, tente consultar `1.3.6.1.2.1.25.3.3.1.2`; se o equipamento retornar instâncias, use um OID completo existente no campo de CPU. Em SNMPv3, use os parâmetros e ferramentas compatíveis com a versão configurada pelo responsável do laboratório.

Faça primeiro um teste sem alertas por e-mail: escolha **Pop-up**, configure temporariamente thresholds baixos e confirme a notificação; depois restaure os limites definidos para a atividade. Para testar o histórico, colete por alguns minutos, escolha um início anterior à coleta e um fim posterior e clique em **Buscar histórico**. O banco `monitor.db` preserva esses dados quando a janela é fechada.

Se não houver resposta, confira se seu computador alcança o IP do roteador, se está na VLAN/rede correta, se o UDP 161 está permitido e se a versão/comunidade/credenciais e a ACL SNMP correspondem às fornecidas. Mensagens de falha aparecem no status da janela e ficam registradas no banco. Não habilite SNMP nem altere comunidade, ACL ou configuração do roteador sem autorização do responsável.

## Métricas e arquitetura

- `ifHCInOctets` / `ifHCOutOctets` (IF-MIB, Counter64): tráfego preferencial; usa `ifInOctets` / `ifOutOctets` (MIB-II, Counter32) como fallback quando os contadores HC não são suportados.
- CPU: OID configurável; o padrão consulta `hrProcessorLoad` da HOST-RESOURCES-MIB.
- Taxa: `(bytes atuais − bytes anteriores) × 8 / intervalo monotônico real`. A primeira amostra não inventa taxa; resets de Counter64, intervalos inválidos e valores acima do plausível são descartados; wrap de Counter32 é tratado.
- O coletor e a taxa ficam nos módulos `app/snmp_client.py` e `app/metrics.py`; a interface fica em `monitor-snmp/app.py`; SQLite, erros e eventos usam `monitor-snmp/app/storage.py`; `monitor-snmp/alert_manager.py` avalia cada threshold e limita alertas repetidos a uma transição ou novo evento após 5 minutos.
- Os alertas por e-mail incluem um resumo HTML com o valor e limite do alerta e cartões separados para IN, OUT e CPU; também levam uma alternativa em texto simples. O e-mail de teste inclui a última amostra disponível. Falhas SNMP são registradas no banco e mostradas no status da janela. Falhas de SMTP também são mostradas sem encerrar o programa.

## Operação

- **Iniciar coleta** inicia um único worker; se estiver pausado, retoma a coleta sem criar outro.
- **Pausar/Retomar** suspende temporariamente as consultas sem apagar amostras.
- Salvar configurações atualiza os parâmetros e thresholds sem reiniciar a aplicação; os novos valores são avaliados na próxima coleta. Se a coleta estiver pausada, clique em **Retomar**.
- **Encerrar** termina o worker e reabilita Iniciar para uma nova execução.
- **Resetar sessão** limpa somente os gráficos e indicadores da sessão aberta. A coleta ativa continua em execução e o histórico SQLite permanece intacto.
- Na aba **Tempo real**, IN e OUT aparecem em gráficos separados lado a lado, com CPU abaixo. O card de CPU permanece destacado enquanto o valor estiver no limite ou acima; ele volta ao normal quando uma coleta indicar recuperação.
- Nos gráficos de tempo real e histórico, passe o cursor sobre um ponto para ver IN, OUT e CPU da mesma amostra; clique no ponto para fixar a leitura e clique nele novamente para liberar. Os três gráficos mostram um cursor vertical sincronizado, e o eixo de tempo reduz a quantidade de rótulos para evitar sobreposição.
- Cada amostra é mantida no histórico SQLite. Eventos que dispararam alerta também são registrados e aparecem como marcadores no gráfico da métrica correspondente ao consultar o período na aba **Histórico**.
- **Histórico** oferece intervalos rápidos (15/30 minutos e 1/3/6/12/24 horas) ou filtro personalizado por início/fim no formato `AAAA-MM-DD HH:MM:SS`; mostra o período e horários das amostras, e indica claramente quando o intervalo está vazio.

## Testes

O histórico salva o limite de CPU usado em cada nova amostra e colore os pontos conforme esse limite, mesmo após uma mudança de configuração. Amostras de bancos antigos não têm esse valor; elas aparecem em cinza como **Limite não registrado**.

```powershell
py -m unittest discover -v
py -m unittest discover -s monitor-snmp -v
```

Os testes automatizados cobrem cálculo de taxas e wraps/reset, armazenamento/filtro/persistência e comportamento dos alertas. Para demonstrar a integração de ponta a ponta, configure um agente SNMP de laboratório, inicie a coleta, provoque tráfego/CPU, consulte um intervalo histórico, teste pausa/reset e use thresholds baixos. E-mail requer SMTP real e configurado.

## Entrega e demonstração

Inclua na entrega o endereço do repositório Git e capturas reais das abas Tempo real, Histórico e Configurações, além de um pop-up de alerta. As capturas dependem de uma sessão gráfica e de um equipamento SNMP configurado; não são simuladas neste repositório. A data e o formato da apresentação são definidos pelo docente.
