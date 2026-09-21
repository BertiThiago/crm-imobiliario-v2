from __future__ import annotations

import re
from pathlib import Path

APP_FILE = Path("/content/crm-imobiliario-v2/app.py")
text = APP_FILE.read_text(encoding="utf-8")

# Imports needed by the operational routes.
if "from whatsapp.safe_queue import" not in text:
    text = text.replace(
        "from flask import",
        "from whatsapp.safe_queue import upsert_contact, enqueue as safe_enqueue\n\nfrom flask import",
        1,
    )
elif "safe_enqueue" not in text:
    text = text.replace(
        "from whatsapp.safe_queue import (",
        "from whatsapp.safe_queue import (",
        1,
    )
    # Add a separate import; avoids fragile editing of an existing multiline block.
    text = text.replace(
        "# ─────────────────────────────────────────────\n# WHATSAPP / SAFE QUEUE",
        "from whatsapp.safe_queue import enqueue as safe_enqueue\n\n# ─────────────────────────────────────────────\n# WHATSAPP / SAFE QUEUE",
        1,
    )

# Ensure manual opt-in endpoint exists.
if "/api/leads/<int:id>/whatsapp-optin" not in text:
    marker = "@app.route('/api/leads/<int:lead_id>/interacoes', methods=['POST'])"
    route = r"""
@app.route('/api/leads/<int:id>/whatsapp-optin', methods=['POST'])
@login_required
def lead_whatsapp_optin(id):
    data = request.get_json(silent=True) or {}
    opt_in = bool(data.get('opt_in'))
    source = str(data.get('source') or ('manual' if opt_in else 'manual_optout')).strip()

    conn = get_db()
    try:
        lead = conn.execute(
            'SELECT id, nome, telefone FROM leads WHERE id=?',
            (id,)
        ).fetchone()
        if not lead:
            return jsonify({'success': False, 'error': 'Lead não encontrado'}), 404

        conn.execute(
            '''UPDATE leads
               SET whatsapp_opt_in=?,
                   whatsapp_opt_in_source=?,
                   whatsapp_opt_in_at=CASE WHEN ?=1 THEN CURRENT_TIMESTAMP ELSE whatsapp_opt_in_at END,
                   whatsapp_opt_out=?,
                   atualizado_em=CURRENT_TIMESTAMP
               WHERE id=?''',
            (1 if opt_in else 0, source, 1 if opt_in else 0, 0 if opt_in else 1, id)
        )
        conn.commit()

        if lead['telefone']:
            upsert_contact(
                phone=lead['telefone'],
                name=lead['nome'] or '',
                opt_in=opt_in,
                opt_in_source=source,
                opt_out=(False if opt_in else True),
            )

        return jsonify({'success': True, 'id': id, 'opt_in': opt_in, 'source': source})
    finally:
        conn.close()

"""
    if marker not in text:
        raise RuntimeError('Não encontrei o ponto seguro para inserir a rota de opt-in.')
    text = text.replace(marker, route + marker, 1)

# Replace the old direct-send campaign starter with Safe Queue.
start = text.find("@app.route('/api/whatsapp/campanhas/<int:id>/iniciar', methods=['POST'])")
if start == -1:
    raise RuntimeError('Rota de início de campanha não encontrada.')
next_route = text.find("\n@app.route(", start + 10)
if next_route == -1:
    raise RuntimeError('Não encontrei a próxima rota após iniciar_campanha.')

new_start = r"""@app.route('/api/whatsapp/campanhas/<int:id>/iniciar', methods=['POST'])
@login_required
def iniciar_campanha(id):
    conn = get_db()
    try:
        campanha = conn.execute(
            'SELECT * FROM mensagens_whatsapp WHERE id=?',
            (id,)
        ).fetchone()
        if not campanha:
            return jsonify({'success': False, 'error': 'Campanha não encontrada'}), 404

        if campanha['status'] in ('Enviando', 'Enfileirada'):
            return jsonify({'success': False, 'error': 'Campanha já está em processamento'}), 409

        contatos = conn.execute(
            '''SELECT * FROM contatos_whatsapp
               WHERE campanha_id=? AND status IN ('Pendente','Erro','Bloqueado')
               ORDER BY id''',
            (id,)
        ).fetchall()

        # Carrega leads uma vez e normaliza telefones para validar opt-in.
        leads = conn.execute(
            '''SELECT nome, telefone, whatsapp_opt_in, whatsapp_opt_out
               FROM leads
               WHERE telefone IS NOT NULL AND telefone <> '' '''
        ).fetchall()
        lead_map = {}
        for lead in leads:
            digits = ''.join(ch for ch in str(lead['telefone']) if ch.isdigit())
            if digits and not digits.startswith('55'):
                digits = '55' + digits
            if digits:
                lead_map[digits] = lead

        enfileirados = 0
        bloqueados = 0
        erros = 0

        for contato in contatos:
            telefone = ''.join(ch for ch in str(contato['telefone'] or '') if ch.isdigit())
            if not telefone:
                conn.execute(
                    'UPDATE contatos_whatsapp SET status=?, erro_msg=? WHERE id=?',
                    ('Erro', 'Telefone inválido', contato['id'])
                )
                erros += 1
                continue
            if not telefone.startswith('55'):
                telefone = '55' + telefone

            lead = lead_map.get(telefone)
            if not lead or not lead['whatsapp_opt_in'] or lead['whatsapp_opt_out']:
                conn.execute(
                    'UPDATE contatos_whatsapp SET status=?, erro_msg=? WHERE id=?',
                    ('Bloqueado', 'Sem opt-in explícito ou com opt-out', contato['id'])
                )
                bloqueados += 1
                continue

            mensagem = str(campanha['mensagem'] or '')
            nome = str(contato['nome'] or lead['nome'] or '')
            mensagem = mensagem.replace('{{nome}}', nome)

            resultado = safe_enqueue(
                phone=telefone,
                message=mensagem,
                require_active=False,
                send_mode='campaign',
                media_path=campanha['media_path'] if 'media_path' in campanha.keys() else None,
                media_name=campanha['media_name'] if 'media_name' in campanha.keys() else None,
                media_type=campanha['media_type'] if 'media_type' in campanha.keys() else None,
                media_mimetype=campanha['media_mimetype'] if 'media_mimetype' in campanha.keys() else None,
                media_caption=campanha['media_caption'] if 'media_caption' in campanha.keys() else None,
            )

            if resultado.get('accepted'):
                conn.execute(
                    'UPDATE contatos_whatsapp SET status=?, erro_msg=NULL WHERE id=?',
                    ('Enfileirado', contato['id'])
                )
                enfileirados += 1
            else:
                conn.execute(
                    'UPDATE contatos_whatsapp SET status=?, erro_msg=? WHERE id=?',
                    ('Bloqueado', resultado.get('reason', 'bloqueado'), contato['id'])
                )
                bloqueados += 1

        novo_status = 'Enviando' if enfileirados else ('Concluido' if not erros else 'Erro')
        conn.execute(
            '''UPDATE mensagens_whatsapp
               SET status=?, iniciado_em=CURRENT_TIMESTAMP,
                   enviados=COALESCE(enviados,0), erros=COALESCE(erros,0)
               WHERE id=?''',
            (novo_status, id)
        )
        conn.commit()

        return jsonify({
            'success': True,
            'status': novo_status,
            'enfileirados': enfileirados,
            'bloqueados': bloqueados,
            'erros': erros,
            'message': 'Campanha colocada na fila segura.'
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

"""
text = text[:start] + new_start + text[next_route:]

# Ensure app.py has media/campaign columns at runtime through a helper migration.
# The notebook also executes an explicit SQLite migration after import, so we do not
# mutate init_db() text here unless needed.

APP_FILE.write_text(text, encoding='utf-8')
print('app.py patched:', APP_FILE)
