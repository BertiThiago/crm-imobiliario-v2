# 🏠 ImobiCRM Pro

> CRM Imobiliário completo para corretores autônomos — Lançamentos + QuintoAndar

---

## ✨ Funcionalidades

| Módulo | Descrição |
|--------|-----------|
| 📊 **Dashboard** | Métricas em tempo real, funil de vendas, VGV, comissões do mês |
| 👥 **Leads** | Cadastro completo, filtros avançados, histórico de interações |
| 🏗 **Kanban** | Funil visual por status (Novo → Fechado) |
| 🤝 **Negócios** | Controle de propostas, contratos, chaves e financiamento |
| 💰 **Comissões** | Controle de recebimentos parciais e totais |
| 🏢 **Empreendimentos** | Cadastro com construtora, tipologia, valores e prazo |
| 🏭 **Construtoras** | Parceiros com contatos e empreendimentos vinculados |
| 📅 **Tarefas** | Agenda com prioridades e alertas de atraso |
| 📱 **Disparo WhatsApp** | Envio em massa com personalização `{{nome}}`, importação CSV |
| ⚙️ **Configurações** | Integração com Evolution API / WPPConnect |

---

## 🚀 Como rodar

### Opção 1 — VSCode / Local (Recomendado)

```bash
# 1. Clone ou extraia o projeto
git clone https://github.com/SEU_USUARIO/crm_imobiliario.git
cd crm_imobiliario

# 2. Instale as dependências
pip install -r requirements.txt

# 3. (Opcional) Popule com dados de demonstração
python seed_demo.py

# 4. Inicie o servidor
python app.py

# Acesse: http://localhost:5000
# Login: admin@crm.com  |  Senha: admin123
```

---

### Opção 2 — Google Colab

```python
# Célula 1: Instalar
!pip install flask flask-cors requests pyngrok --quiet
!git clone https://github.com/SEU_USUARIO/crm_imobiliario.git

# Célula 2: Iniciar com túnel público
import subprocess, threading, time
from pyngrok import ngrok

ngrok.set_auth_token("SEU_TOKEN_NGROK")  # ngrok.com (grátis)

def run():
    subprocess.run(["python", "app.py"], cwd="/content/crm_imobiliario")

threading.Thread(target=run, daemon=True).start()
time.sleep(3)

url = ngrok.connect(5000)
print(f"🔗 CRM online em: {url}")
```

---

### Opção 3 — Docker

```bash
# Build e rodar
docker-compose up -d

# Ver logs
docker-compose logs -f

# Parar
docker-compose down
```

---

### Opção 4 — VPS Linux (Ubuntu)

```bash
# 1. Instalar dependências
sudo apt update && sudo apt install python3-pip git -y
pip3 install flask flask-cors requests

# 2. Clonar o projeto
git clone https://github.com/SEU_USUARIO/crm_imobiliario.git /opt/crm_imobiliario
cd /opt/crm_imobiliario

# 3. Configurar como serviço
sudo cp imobicrm.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now imobicrm

# 4. (Opcional) Nginx como proxy reverso
sudo apt install nginx -y
# Configure /etc/nginx/sites-available/crm:
#   location / { proxy_pass http://127.0.0.1:5000; }
```

---

## 📱 Integração WhatsApp (Disparo em Massa)

O sistema usa a **Evolution API** (open source, gratuita) para envio real.

### Setup rápido com Docker:

```bash
docker run -d \
  --name evolution-api \
  -p 8080:8080 \
  -e AUTHENTICATION_API_KEY=sua_chave_aqui \
  atendai/evolution-api:latest
```

1. Acesse `http://localhost:8080/manager`
2. Crie uma instância e escaneie o QR Code
3. No CRM → Configurações → cole a URL e o token
4. Crie uma campanha em **Disparo WhatsApp**

> **Sem API configurada**: o sistema opera em **modo simulação** (processa mas não envia de fato).

---

## 🗄️ Banco de Dados

SQLite local em `database/crm.db`. Tabelas principais:

```
usuarios → construtoras → empreendimentos
                              ↓
leads ←→ interacoes       negocios → comissoes
leads ←→ tarefas
mensagens_whatsapp → contatos_whatsapp
```

---

## 🔑 Credenciais Padrão

| Campo | Valor |
|-------|-------|
| Email | `admin@crm.com` |
| Senha | `admin123` |

> Mude a senha em produção editando diretamente o banco ou adicionando endpoint `/api/perfil`.

---

## 🛠️ Tecnologias

- **Backend**: Python 3.11 + Flask
- **Banco**: SQLite (zero configuração)
- **Frontend**: HTML5 + CSS3 + JavaScript puro (sem dependências externas de JS)
- **WhatsApp**: Evolution API / WPPConnect (opcional)
- **Deploy**: Docker, systemd, Google Colab + ngrok

---

## 📂 Estrutura do Projeto

```
crm_imobiliario/
├── app.py                  # API Flask completa
├── requirements.txt        # Dependências Python
├── seed_demo.py            # Dados de demonstração
├── colab_setup.py          # Script para Google Colab
├── Dockerfile              # Container Docker
├── docker-compose.yml      # Orquestração Docker
├── imobicrm.service        # Serviço Linux (systemd)
├── templates/
│   └── index.html          # Frontend SPA completo
├── database/
│   └── crm.db              # Banco SQLite (gerado automaticamente)
├── tests/
│   └── test_app.py         # Testes automatizados
└── .github/
    └── workflows/
        └── ci.yml          # GitHub Actions CI/CD
```

---

## 🗺️ Roadmap

- [ ] Relatórios PDF exportáveis
- [ ] App mobile (PWA)
- [ ] Multi-usuário com permissões
- [ ] Integração portal ImóvelWeb / ZAP via scraping
- [ ] Notificações por e-mail (SMTP)
- [ ] Calendário com Google Calendar sync
- [ ] IA para scoring de leads

---

**Desenvolvido para corretores autônomos que trabalham com Lançamentos e QuintoAndar.**
