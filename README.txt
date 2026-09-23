BERTI OPERACIONAL v3

Arquivos:
- BERTI_Evolution_Colab_OPERACIONAL_v3.ipynb -> notebook operacional reconstruído
- index_BERTI_OPERACIONAL.html -> frontend atualizado
- safe_queue_operacional.py -> fila segura com opt-in/opt-out + campaign/service + mídia
- worker_safe_operacional.py -> worker real contínuo com texto/mídia e delay 8-20s
- evolution_sender_operacional.py -> envio Evolution texto/mídia
- app_patch_operacional.py -> correção do backend: opt-in manual + campanha via Safe Queue

Fluxo:
1. Abrir o notebook no Google Colab.
2. Executar células em ordem.
3. Escanear QR se a instância não estiver OPEN.
4. O notebook executa smoke tests sem envio.
5. Na célula de ativação, digitar INICIAR para ligar o worker real.
6. Criar/iniciar campanhas pelo frontend.

IMPORTANTE:
- Campanhas só entram na fila para leads com whatsapp_opt_in=1 e whatsapp_opt_out=0.
- O worker real não inicia sem confirmação explícita.
- A fila persistente fica em Google Drive/BERTI_BOT/safe_queue.db.
- Mídias ficam em Google Drive/BERTI_BOT/campanhas/midias.
