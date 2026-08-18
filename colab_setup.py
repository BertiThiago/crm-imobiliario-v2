# ╔══════════════════════════════════════════════════════════╗
# ║          ImobiCRM Pro — Setup para Google Colab          ║
# ╚══════════════════════════════════════════════════════════╝
# Cole este notebook no Google Colab e execute célula por célula

# ─── CÉLULA 1: Instalar dependências ───────────────────────
!pip install flask flask-cors requests pyngrok --quiet

# ─── CÉLULA 2: Baixar o projeto do GitHub (se necessário) ──
# Se você subiu para o GitHub, use:
# !git clone https://github.com/SEU_USUARIO/crm_imobiliario.git
# %cd crm_imobiliario

# ─── CÉLULA 3: Iniciar o CRM com ngrok (tunnel público) ────
import subprocess, threading, time
from pyngrok import ngrok

# Configura ngrok (crie conta gratuita em ngrok.com e cole seu token)
NGROK_TOKEN = "SEU_TOKEN_NGROK_AQUI"  # <- substitua pelo seu token

ngrok.set_auth_token(NGROK_TOKEN)

# Inicia o servidor Flask em background
def run_flask():
    subprocess.run(["python", "app.py"], cwd="/content/crm_imobiliario")

thread = threading.Thread(target=run_flask, daemon=True)
thread.start()
time.sleep(3)

# Cria o túnel público
public_url = ngrok.connect(5000)
print(f"\n{'='*50}")
print(f"  🏠 ImobiCRM Pro está ONLINE!")
print(f"  🔗 URL: {public_url}")
print(f"  👤 Login: admin@crm.com")
print(f"  🔑 Senha: admin123")
print(f"{'='*50}\n")
