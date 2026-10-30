from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
import sqlite3
import json
import os
import hashlib
import io
import csv
import re as _re
import unicodedata as _unicodedata
import uuid
from datetime import datetime, timedelta, date
import requests
import time
import threading
from urllib.parse import urljoin
from werkzeug.utils import secure_filename
from pathlib import Path

# ─────────────────────────────────────────────
# WHATSAPP / SAFE QUEUE
# ─────────────────────────────────────────────

from whatsapp.safe_queue import (
    register_incoming,
    upsert_contact,
    dashboard as safe_dashboard_data,
    list_queue as safe_queue_list,
    enqueue as safe_enqueue,
    update_message_status,
    connect as safe_queue_connect,
    recover_stuck,
    cancel_pending,
    upsert_contact,
)

app = Flask(__name__)
app.secret_key = os.getenv('CRM_SECRET_KEY', 'crm_imobiliario_secret_2024')
CORS(app)

# ─────────────────────────────────────────────
# ARMAZENAMENTO PERSISTENTE
# ─────────────────────────────────────────────

CRM_DATA_ROOT = Path(
    os.getenv(
        "CRM_DATA_ROOT",
        "/content/drive/MyDrive/BERTI_BOT"
    )
)

DATABASE_ROOT = CRM_DATA_ROOT / "database"
CRM_IMPORT_ROOT = Path(os.getenv("CRM_IMPORT_ROOT", str(CRM_DATA_ROOT / "importacao")))
DB_PATH = DATABASE_ROOT / "crm.db"

# ─────────────────────────────────────────────
# WHATSAPP / MÍDIAS DE CAMPANHAS
# ─────────────────────────────────────────────

MEDIA_ROOT = Path(
    os.getenv(
        "CRM_MEDIA_ROOT",
        str(
            DATABASE_ROOT
            / "campanhas"
            / "midias"
        )
    )
)

MEDIA_ROOT.mkdir(
    parents=True,
    exist_ok=True
)

ALLOWED_MEDIA = {
    "image": {
        "image/jpeg",
        "image/png",
        "image/webp",
    },
    "video": {
        "video/mp4",
    },
}

MAX_MEDIA_SIZE = 64 * 1024 * 1024  # 64 MB

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DATABASE_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    MEDIA_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            telefone TEXT,
            creci TEXT,
            foto TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS construtoras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cnpj TEXT,
            contato_nome TEXT,
            contato_telefone TEXT,
            contato_email TEXT,
            site TEXT,
            logo TEXT,
            observacoes TEXT,
            ativa INTEGER DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS empreendimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            construtora_id INTEGER,
            nome TEXT NOT NULL,
            tipo TEXT,
            endereco TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            cep TEXT,
            valor_min REAL,
            valor_max REAL,
            area_min REAL,
            area_max REAL,
            quartos_min INTEGER,
            quartos_max INTEGER,
            vagas_min INTEGER,
            vagas_max INTEGER,
            data_lancamento DATE,
            data_entrega DATE,
            status TEXT DEFAULT 'Em Lançamento',
            descricao TEXT,
            foto_capa TEXT,
            link_material TEXT,
            comissao_percentual REAL,
            ativo INTEGER DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (construtora_id) REFERENCES construtoras(id)
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            cpf TEXT,
            origem TEXT,
            tipo_interesse TEXT DEFAULT 'Lancamento',
            empreendimento_id INTEGER,
            status TEXT DEFAULT 'Novo',
            temperatura TEXT DEFAULT 'Frio',
            valor_interesse REAL,
            observacoes TEXT,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            responsavel_id INTEGER,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empreendimento_id) REFERENCES empreendimentos(id),
            FOREIGN KEY (responsavel_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS interacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
            usuario_id INTEGER,
            agendamento DATETIME,
            concluido INTEGER DEFAULT 1,
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS negocios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            empreendimento_id INTEGER,
            tipo TEXT DEFAULT 'Lancamento',
            status TEXT DEFAULT 'Proposta',
            valor_venda REAL,
            valor_comissao REAL,
            percentual_comissao REAL,
            data_proposta DATE,
            data_contrato DATE,
            data_previsao_chaves DATE,
            data_entrega_chaves DATE,
            numero_contrato TEXT,
            unidade TEXT,
            bloco TEXT,
            andar INTEGER,
            financiamento INTEGER DEFAULT 0,
            banco_financiamento TEXT,
            valor_financiado REAL,
            valor_entrada REAL,
            data_aprovacao_financiamento DATE,
            observacoes TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (empreendimento_id) REFERENCES empreendimentos(id)
        );

        CREATE TABLE IF NOT EXISTS comissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            negocio_id INTEGER NOT NULL,
            valor_total REAL,
            valor_recebido REAL DEFAULT 0,
            status TEXT DEFAULT 'Pendente',
            data_previsao DATE,
            data_recebimento DATE,
            observacoes TEXT,
            FOREIGN KEY (negocio_id) REFERENCES negocios(id)
        );

        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descricao TEXT,
            lead_id INTEGER,
            negocio_id INTEGER,
            responsavel_id INTEGER,
            data_vencimento DATETIME,
            prioridade TEXT DEFAULT 'Media',
            status TEXT DEFAULT 'Pendente',
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (negocio_id) REFERENCES negocios(id)
        );

        CREATE TABLE IF NOT EXISTS mensagens_whatsapp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_campanha TEXT NOT NULL,
            mensagem TEXT NOT NULL,
            lista_contatos TEXT,
            status TEXT DEFAULT 'Rascunho',
            total_contatos INTEGER DEFAULT 0,
            enviados INTEGER DEFAULT 0,
            erros INTEGER DEFAULT 0,
            intervalo_segundos INTEGER DEFAULT 5,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            iniciado_em DATETIME,
            concluido_em DATETIME
        );

        CREATE TABLE IF NOT EXISTS contatos_whatsapp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campanha_id INTEGER,
            nome TEXT,
            telefone TEXT NOT NULL,
            status TEXT DEFAULT 'Pendente',
            enviado_em DATETIME,
            erro_msg TEXT,
            FOREIGN KEY (campanha_id) REFERENCES mensagens_whatsapp(id)
        );

        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );

        -- ── TABELA DE UNIDADES (tabelão das construtoras) ──────────
        CREATE TABLE IF NOT EXISTS unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empreendimento_id INTEGER NOT NULL,
            -- Identificação
            bloco TEXT,
            andar INTEGER,
            unidade TEXT NOT NULL,
            -- Produto
            tipologia TEXT,          -- Ex: "2 dorms", "3 dorms + suíte"
            area_privativa REAL,
            area_total REAL,
            quartos INTEGER,
            suites INTEGER,
            banheiros INTEGER,
            vagas INTEGER,
            orientacao TEXT,         -- Sol nascente, poente, frente, fundos
            -- Financeiro
            valor_tabela REAL,
            valor_desconto REAL,
            percentual_desconto REAL,
            -- Status
            disponibilidade TEXT DEFAULT 'Disponível',  -- Disponível / Reservado / Vendido / Bloqueado
            data_reserva DATE,
            observacoes TEXT,
            -- Controle
            importado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            fonte TEXT,              -- nome do arquivo de origem
            FOREIGN KEY (empreendimento_id) REFERENCES empreendimentos(id)
        );

        -- ── LOG DE IMPORTAÇÕES ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS importacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,           -- 'book', 'tabela_valores', 'leads_csv'
            arquivo_nome TEXT,
            total_registros INTEGER DEFAULT 0,
            importados INTEGER DEFAULT 0,
            erros INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Concluido',
            log_detalhado TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # Usuário padrão
    senha_hash = hashlib.sha256('admin123'.encode()).hexdigest()
    c.execute('''INSERT OR IGNORE INTO usuarios (nome, email, senha, creci)
                 VALUES (?, ?, ?, ?)''',
              ('Corretor Admin', 'admin@crm.com', senha_hash, 'CRECI-SP 00000'))

    # Config padrão
    configs = [
        ('whatsapp_api_url', ''),
        ('whatsapp_token', ''),
        ('nome_corretor', 'Meu CRM Imobiliário'),
        ('quintoandar_ativo', '1'),
    ]
    for k, v in configs:
        c.execute(
            'INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)',
            (k, v)
        )

    # ─────────────────────────────────────────
    # MIGRAÇÃO — OPT-IN / OPT-OUT DO WHATSAPP
    # ─────────────────────────────────────────

    lead_columns = {
        row["name"]
        for row in c.execute(
            "PRAGMA table_info(leads)"
        ).fetchall()
    }

    lead_fields = {
        "whatsapp_opt_in": "INTEGER NOT NULL DEFAULT 0",
        "whatsapp_opt_in_source": "TEXT",
        "whatsapp_opt_in_at": "DATETIME",
        "whatsapp_opt_out": "INTEGER NOT NULL DEFAULT 0",
        "arquivado": "INTEGER NOT NULL DEFAULT 0",
        "arquivado_em": "DATETIME",
        "motivo_arquivamento": "TEXT",
    }

    for column, definition in lead_fields.items():
        if column not in lead_columns:
            c.execute(
                f"ALTER TABLE leads ADD COLUMN {column} {definition}"
            )

    # ─────────────────────────────────────────
    # MIGRAÇÃO — MÍDIA DAS CAMPANHAS
    # ─────────────────────────────────────────

    campaign_columns = {
        row["name"]
        for row in c.execute(
            "PRAGMA table_info(mensagens_whatsapp)"
        ).fetchall()
    }

    campaign_fields = {
        "media_path": "TEXT",
        "media_name": "TEXT",
        "media_type": "TEXT",
        "media_mimetype": "TEXT",
        "media_caption": "TEXT",
        "botoes": "TEXT",
        "edicoes_log": "TEXT",
        "duplicada_de": "INTEGER",
    }

    for column, definition in campaign_fields.items():
        if column not in campaign_columns:
            c.execute(
                f"ALTER TABLE mensagens_whatsapp ADD COLUMN {column} {definition}"
            )

    contato_columns = {
        row["name"]
        for row in c.execute(
            "PRAGMA table_info(contatos_whatsapp)"
        ).fetchall()
    }
    if "queue_id" not in contato_columns:
        c.execute(
            "ALTER TABLE contatos_whatsapp ADD COLUMN queue_id TEXT"
        )
    for _coluna, _definicao in (("resposta", "TEXT"), ("respondido_em", "DATETIME")):
        if _coluna not in contato_columns:
            c.execute(
                f"ALTER TABLE contatos_whatsapp ADD COLUMN {_coluna} {_definicao}"
            )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS campanha_midias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campanha_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 1,
            media_path TEXT NOT NULL,
            media_name TEXT,
            media_type TEXT,
            media_mimetype TEXT,
            legenda TEXT DEFAULT ''
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS contato_fila (
            contato_id INTEGER NOT NULL,
            queue_id TEXT NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (contato_id, queue_id)
        )
        """
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS respostas_processadas (message_id TEXT PRIMARY KEY, criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS status_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
            ordem INTEGER NOT NULL DEFAULT 0,
            cor TEXT DEFAULT '',
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for _nome, _ordem, _cor in (
        ('Novo', 1, '#3b82f6'), ('Contato', 2, '#e8a020'), ('Visita', 3, '#a855f7'),
        ('Proposta', 4, '#f5c842'), ('Contrato', 5, '#4ade80'), ('Fechado', 6, '#22c55e'),
        ('Perdido', 9999, '#ef4444'),
    ):
        c.execute(
            "INSERT OR IGNORE INTO status_leads (nome, ordem, cor) VALUES (?, ?, ?)",
            (_nome, _ordem, _cor),
        )
    # status que ja existem nos leads mas ainda nao estao na tabela
    for _linha in c.execute(
        "SELECT DISTINCT TRIM(status) FROM leads WHERE status IS NOT NULL AND TRIM(status) <> ''"
    ).fetchall():
        _prox = (c.execute(
            "SELECT COALESCE(MAX(ordem), 0) FROM status_leads WHERE ordem < 9999"
        ).fetchone()[0] or 0) + 1
        c.execute(
            "INSERT OR IGNORE INTO status_leads (nome, ordem, cor) VALUES (?, ?, '#64748b')",
            (_linha[0], _prox),
        )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS modelos_mensagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
            texto TEXT NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    MEDIA_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )
    try:
        CRM_IMPORT_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado!")

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Não autenticado'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    senha_hash = hashlib.sha256(data['senha'].encode()).hexdigest()
    conn = get_db()
    user = conn.execute('SELECT * FROM usuarios WHERE email=? AND senha=?',
                        (data['email'], senha_hash)).fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        session['user_nome'] = user['nome']
        return jsonify({'success': True, 'nome': user['nome'], 'id': user['id']})
    return jsonify({'success': False, 'error': 'Credenciais inválidas'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/me')
def me():
    if 'user_id' in session:
        return jsonify({'logado': True, 'nome': session['user_nome'], 'id': session['user_id']})
    return jsonify({'logado': False})

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

@app.route('/api/dashboard')
@login_required
def dashboard():
    conn = get_db()
    hoje = datetime.now().strftime('%Y-%m-%d')
    mes_inicio = datetime.now().replace(day=1).strftime('%Y-%m-%d')

    stats = {
        'leads_total': conn.execute('SELECT COUNT(*) FROM leads WHERE COALESCE(arquivado,0)=0').fetchone()[0],
        'leads_mes': conn.execute('SELECT COUNT(*) FROM leads WHERE COALESCE(arquivado,0)=0 AND criado_em >= ?', (mes_inicio,)).fetchone()[0],
        'leads_novos': conn.execute('SELECT COUNT(*) FROM leads WHERE COALESCE(arquivado,0)=0 AND status="Novo"').fetchone()[0],
        'negocios_abertos': conn.execute('SELECT COUNT(*) FROM negocios WHERE status NOT IN ("Fechado","Cancelado")').fetchone()[0],
        'negocios_fechados_mes': conn.execute('SELECT COUNT(*) FROM negocios WHERE status="Fechado" AND data_contrato >= ?', (mes_inicio,)).fetchone()[0],
        'vgv_mes': conn.execute('SELECT COALESCE(SUM(valor_venda),0) FROM negocios WHERE status="Fechado" AND data_contrato >= ?', (mes_inicio,)).fetchone()[0],
        'comissao_mes': conn.execute('SELECT COALESCE(SUM(valor_comissao),0) FROM negocios WHERE status="Fechado" AND data_contrato >= ?', (mes_inicio,)).fetchone()[0],
        'tarefas_hoje': conn.execute('SELECT COUNT(*) FROM tarefas WHERE DATE(data_vencimento)=? AND status="Pendente"', (hoje,)).fetchone()[0],
        'tarefas_atrasadas': conn.execute('SELECT COUNT(*) FROM tarefas WHERE DATE(data_vencimento)<? AND status="Pendente"', (hoje,)).fetchone()[0],
    }

    # Funil de leads
    funil = conn.execute('''SELECT l.status AS status, COUNT(*) AS total, COALESCE(s.cor, '') AS cor
        FROM leads l LEFT JOIN status_leads s ON s.nome = l.status
        WHERE COALESCE(l.arquivado,0)=0
        GROUP BY l.status ORDER BY COALESCE(s.ordem, 5000), l.status''').fetchall()

    # Leads por origem
    origens = conn.execute('SELECT origem, COUNT(*) as total FROM leads WHERE COALESCE(arquivado,0)=0 GROUP BY origem ORDER BY total DESC LIMIT 6').fetchall()

    # Últimos leads
    ultimos_leads = conn.execute('''SELECT l.*, e.nome as empreendimento FROM leads l
        LEFT JOIN empreendimentos e ON l.empreendimento_id=e.id
        WHERE COALESCE(l.arquivado,0)=0
        ORDER BY l.criado_em DESC LIMIT 8''').fetchall()

    # Tarefas do dia
    tarefas = conn.execute('''SELECT t.*, l.nome as lead_nome FROM tarefas t
        LEFT JOIN leads l ON t.lead_id=l.id
        WHERE DATE(t.data_vencimento)=? AND t.status="Pendente"
        ORDER BY t.prioridade DESC''', (hoje,)).fetchall()

    conn.close()
    return jsonify({
        'stats': stats,
        'funil': [dict(r) for r in funil],
        'origens': [dict(r) for r in origens],
        'ultimos_leads': [dict(r) for r in ultimos_leads],
        'tarefas': [dict(r) for r in tarefas]
    })

# ─────────────────────────────────────────────
# CONSTRUTORAS
# ─────────────────────────────────────────────

@app.route('/api/construtoras', methods=['GET', 'POST'])
@login_required
def construtoras():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('''SELECT c.*, COUNT(e.id) as total_empreendimentos
            FROM construtoras c LEFT JOIN empreendimentos e ON e.construtora_id=c.id
            WHERE c.ativa=1 GROUP BY c.id ORDER BY c.nome''').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json
    conn.execute('''INSERT INTO construtoras (nome,cnpj,contato_nome,contato_telefone,contato_email,site,observacoes)
        VALUES (?,?,?,?,?,?,?)''',
        (data['nome'], data.get('cnpj',''), data.get('contato_nome',''),
         data.get('contato_telefone',''), data.get('contato_email',''),
         data.get('site',''), data.get('observacoes','')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/construtoras/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def construtora_detail(id):
    conn = get_db()
    if request.method == 'GET':
        row = conn.execute('SELECT * FROM construtoras WHERE id=?', (id,)).fetchone()
        conn.close()
        return jsonify(dict(row) if row else {})
    if request.method == 'PUT':
        data = request.json
        conn.execute('''UPDATE construtoras SET nome=?,cnpj=?,contato_nome=?,contato_telefone=?,
            contato_email=?,site=?,observacoes=? WHERE id=?''',
            (data['nome'], data.get('cnpj',''), data.get('contato_nome',''),
             data.get('contato_telefone',''), data.get('contato_email',''),
             data.get('site',''), data.get('observacoes',''), id))
        conn.commit(); conn.close()
        return jsonify({'success': True})
    conn.execute('UPDATE construtoras SET ativa=0 WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# EMPREENDIMENTOS
# ─────────────────────────────────────────────

@app.route('/api/empreendimentos', methods=['GET', 'POST'])
@login_required
def empreendimentos():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('''SELECT e.*, c.nome as construtora_nome,
            COUNT(l.id) as total_leads FROM empreendimentos e
            LEFT JOIN construtoras c ON e.construtora_id=c.id
            LEFT JOIN leads l ON l.empreendimento_id=e.id
            WHERE e.ativo=1 GROUP BY e.id ORDER BY e.nome''').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json
    conn.execute('''INSERT INTO empreendimentos
        (construtora_id,nome,tipo,endereco,bairro,cidade,estado,cep,valor_min,valor_max,
         area_min,area_max,quartos_min,quartos_max,vagas_min,vagas_max,data_lancamento,
         data_entrega,status,descricao,link_material,comissao_percentual)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data.get('construtora_id'), data['nome'], data.get('tipo','Apartamento'),
         data.get('endereco',''), data.get('bairro',''), data.get('cidade',''),
         data.get('estado','SP'), data.get('cep',''),
         data.get('valor_min',0), data.get('valor_max',0),
         data.get('area_min',0), data.get('area_max',0),
         data.get('quartos_min',1), data.get('quartos_max',4),
         data.get('vagas_min',0), data.get('vagas_max',2),
         data.get('data_lancamento'), data.get('data_entrega'),
         data.get('status','Em Lançamento'), data.get('descricao',''),
         data.get('link_material',''), data.get('comissao_percentual',0.5)))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/empreendimentos/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def empreendimento_detail(id):
    conn = get_db()
    if request.method == 'GET':
        row = conn.execute('''SELECT e.*, c.nome as construtora_nome FROM empreendimentos e
            LEFT JOIN construtoras c ON e.construtora_id=c.id WHERE e.id=?''', (id,)).fetchone()
        conn.close()
        return jsonify(dict(row) if row else {})
    if request.method == 'PUT':
        data = request.json
        conn.execute('''UPDATE empreendimentos SET construtora_id=?,nome=?,tipo=?,endereco=?,
            bairro=?,cidade=?,estado=?,cep=?,valor_min=?,valor_max=?,area_min=?,area_max=?,
            quartos_min=?,quartos_max=?,vagas_min=?,vagas_max=?,data_lancamento=?,data_entrega=?,
            status=?,descricao=?,link_material=?,comissao_percentual=? WHERE id=?''',
            (data.get('construtora_id'), data['nome'], data.get('tipo','Apartamento'),
             data.get('endereco',''), data.get('bairro',''), data.get('cidade',''),
             data.get('estado','SP'), data.get('cep',''),
             data.get('valor_min',0), data.get('valor_max',0),
             data.get('area_min',0), data.get('area_max',0),
             data.get('quartos_min',1), data.get('quartos_max',4),
             data.get('vagas_min',0), data.get('vagas_max',2),
             data.get('data_lancamento'), data.get('data_entrega'),
             data.get('status'), data.get('descricao',''),
             data.get('link_material',''), data.get('comissao_percentual',0.5), id))
        conn.commit(); conn.close()
        return jsonify({'success': True})
    conn.execute('UPDATE empreendimentos SET ativo=0 WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# LEADS
# ─────────────────────────────────────────────

@app.route('/api/leads', methods=['GET', 'POST'])
@login_required
def leads():
    conn = get_db()
    if request.method == 'GET':
        filtros = []
        params = []
        arquivados = request.args.get('arquivados', 'nao')
        if arquivados == 'sim':
            filtros.append('COALESCE(l.arquivado, 0)=1')
        elif arquivados != 'todos':
            filtros.append('COALESCE(l.arquivado, 0)=0')
        if request.args.get('status'):
            filtros.append('l.status=?'); params.append(request.args['status'])
        if request.args.get('temperatura'):
            filtros.append('l.temperatura=?'); params.append(request.args['temperatura'])
        if request.args.get('tipo_interesse'):
            filtros.append('l.tipo_interesse=?'); params.append(request.args['tipo_interesse'])
        if request.args.get('empreendimento_id'):
            filtros.append('l.empreendimento_id=?'); params.append(request.args['empreendimento_id'])
        if request.args.get('busca'):
            filtros.append('(l.nome LIKE ? OR l.telefone LIKE ? OR l.email LIKE ?)')
            b = f"%{request.args['busca']}%"
            params.extend([b, b, b])
        where = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''
        rows = conn.execute(f'''SELECT l.*, e.nome as empreendimento,
            u.nome as responsavel FROM leads l
            LEFT JOIN empreendimentos e ON l.empreendimento_id=e.id
            LEFT JOIN usuarios u ON l.responsavel_id=u.id
            {where} ORDER BY l.criado_em DESC''', params).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json
    conn.execute('''INSERT INTO leads
        (nome,telefone,email,cpf,origem,tipo_interesse,empreendimento_id,status,
         temperatura,valor_interesse,observacoes,utm_source,utm_medium,utm_campaign,responsavel_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data['nome'], data.get('telefone',''), data.get('email',''), data.get('cpf',''),
         data.get('origem','Direto'), data.get('tipo_interesse','Lancamento'),
         data.get('empreendimento_id'), _garantir_status_lead(conn, data.get('status','Novo'))[0],
         data.get('temperatura','Frio'), data.get('valor_interesse'),
         data.get('observacoes',''), data.get('utm_source',''),
         data.get('utm_medium',''), data.get('utm_campaign',''),
         session['user_id']))
    conn.commit(); conn.close()
    return jsonify({'success': True})

def _alterar_arquivamento(conn, ids, arquivar, motivo=''):
    """Arquiva ou desarquiva leads e registra a acao no historico de cada um.
    Arquivar nao apaga nada e nao muda opt-in/opt-out: so tira o lead das listas e das campanhas."""
    ids = sorted({int(i) for i in ids if str(i).isdigit()})
    motivo = ' '.join(str(motivo or '').split())[:200]
    alterados = 0
    for i in range(0, len(ids), 400):
        bloco = ids[i:i + 400]
        marcas = ','.join('?' * len(bloco))
        alvo = 0 if arquivar else 1
        rows = conn.execute(
            f"SELECT id FROM leads WHERE id IN ({marcas}) AND COALESCE(arquivado, 0)=?", bloco + [alvo]
        ).fetchall()
        for r in rows:
            if arquivar:
                conn.execute(
                    "UPDATE leads SET arquivado=1, arquivado_em=CURRENT_TIMESTAMP, motivo_arquivamento=? WHERE id=?",
                    (motivo, r['id']),
                )
            else:
                conn.execute(
                    "UPDATE leads SET arquivado=0, arquivado_em=NULL, motivo_arquivamento=NULL WHERE id=?", (r['id'],)
                )
            conn.execute(
                "INSERT INTO interacoes (lead_id, tipo, descricao, concluido, usuario_id) VALUES (?,?,?,1,?)",
                (r['id'], 'Nota',
                 ('Lead arquivado' + (f': {motivo}' if motivo else '')) if arquivar else 'Lead desarquivado',
                 session.get('user_id')),
            )
            alterados += 1
    return alterados


@app.route('/api/leads/<int:id>/arquivar', methods=['POST'])
@login_required
def arquivar_lead(id):
    motivo = (request.get_json(silent=True) or {}).get('motivo', '')
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM leads WHERE id=?", (id,)).fetchone():
            return jsonify({'success': False, 'error': 'Lead não encontrado'}), 404
        n = _alterar_arquivamento(conn, [id], True, motivo)
        conn.commit()
        return jsonify({'success': True, 'alterados': n})
    finally:
        conn.close()


@app.route('/api/leads/<int:id>/desarquivar', methods=['POST'])
@login_required
def desarquivar_lead(id):
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM leads WHERE id=?", (id,)).fetchone():
            return jsonify({'success': False, 'error': 'Lead não encontrado'}), 404
        n = _alterar_arquivamento(conn, [id], False)
        conn.commit()
        return jsonify({'success': True, 'alterados': n})
    finally:
        conn.close()


@app.route('/api/leads/arquivar-lote', methods=['POST'])
@login_required
def arquivar_leads_em_lote():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    acao = str(data.get('acao') or 'arquivar')
    if acao not in ('arquivar', 'desarquivar'):
        return jsonify({'success': False, 'error': "acao deve ser 'arquivar' ou 'desarquivar'"}), 400
    if not isinstance(ids, list) or not ids:
        return jsonify({'success': False, 'error': 'Selecione ao menos um lead.'}), 400
    if len(ids) > 2000:
        return jsonify({'success': False, 'error': 'Limite de 2.000 leads por vez.'}), 400
    conn = get_db()
    try:
        n = _alterar_arquivamento(conn, ids, acao == 'arquivar', data.get('motivo', ''))
        conn.commit()
        return jsonify({'success': True, 'alterados': n, 'ignorados': len(set(map(str, ids))) - n})
    finally:
        conn.close()


@app.route('/api/leads/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def lead_detail(id):
    conn = get_db()
    if request.method == 'GET':
        lead = conn.execute('''SELECT l.*, e.nome as empreendimento, c.nome as construtora,
            u.nome as responsavel FROM leads l
            LEFT JOIN empreendimentos e ON l.empreendimento_id=e.id
            LEFT JOIN construtoras c ON e.construtora_id=c.id
            LEFT JOIN usuarios u ON l.responsavel_id=u.id
            WHERE l.id=?''', (id,)).fetchone()
        interacoes = conn.execute('''SELECT i.*, u.nome as usuario FROM interacoes i
            LEFT JOIN usuarios u ON i.usuario_id=u.id
            WHERE i.lead_id=? ORDER BY i.data_hora DESC''', (id,)).fetchall()
        negocios = conn.execute('''SELECT n.*, e.nome as empreendimento FROM negocios n
            LEFT JOIN empreendimentos e ON n.empreendimento_id=e.id
            WHERE n.lead_id=?''', (id,)).fetchall()
        conn.close()
        return jsonify({
            'lead': dict(lead) if lead else {},
            'interacoes': [dict(i) for i in interacoes],
            'negocios': [dict(n) for n in negocios]
        })
    if request.method == 'PUT':
        data = request.json
        conn.execute('''UPDATE leads SET nome=?,telefone=?,email=?,cpf=?,origem=?,
            tipo_interesse=?,empreendimento_id=?,status=?,temperatura=?,
            valor_interesse=?,observacoes=?,atualizado_em=CURRENT_TIMESTAMP WHERE id=?''',
            (data['nome'], data.get('telefone',''), data.get('email',''), data.get('cpf',''),
             data.get('origem',''), data.get('tipo_interesse','Lancamento'),
             data.get('empreendimento_id'), _garantir_status_lead(conn, data.get('status','Novo'))[0],
             data.get('temperatura','Frio'), data.get('valor_interesse'),
             data.get('observacoes',''), id))
        conn.commit(); conn.close()
        return jsonify({'success': True})
    conn.execute('DELETE FROM leads WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# INTERAÇÕES
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# WHATSAPP — OPT-IN / OPT-OUT MANUAL DO LEAD
# ─────────────────────────────────────────────

@app.route(
    '/api/leads/<int:id>/whatsapp-optin',
    methods=['PUT']
)
@login_required
def atualizar_whatsapp_optin(id):

    data = request.get_json(silent=True) or {}

    opt_in = bool(
        data.get(
            "opt_in",
            False
        )
    )

    source = str(
        data.get(
            "source",
            "Manual"
        )
    ).strip()

    conn = get_db()

    try:

        lead = conn.execute(
            """
            SELECT
                id,
                nome,
                telefone
            FROM leads
            WHERE id=?
            """,
            (id,)
        ).fetchone()

        if not lead:
            return jsonify({
                "success": False,
                "error": "Lead não encontrado"
            }), 404

        if opt_in:

            now_value = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            opt_out_value = 0

            source_value = source or "Manual"

        else:

            now_value = None

            opt_out_value = 1

            source_value = ""

        conn.execute(
            """
            UPDATE leads
            SET
                whatsapp_opt_in=?,
                whatsapp_opt_in_source=?,
                whatsapp_opt_in_at=?,
                whatsapp_opt_out=?,
                atualizado_em=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                int(opt_in),
                source_value,
                now_value,
                opt_out_value,
                id
            )
        )

        conn.commit()

    finally:
        conn.close()

    telefone = str(
        lead["telefone"] or ""
    ).strip()

    if telefone:

        try:

            upsert_contact(
                phone=telefone,
                name=lead["nome"] or "",
                opt_in=opt_in,
                opt_in_source=source_value,
                opt_in_at=now_value,
                opt_out=bool(
                    opt_out_value
                )
            )

        except Exception as exc:

            print(
                "⚠️ Falha ao sincronizar "
                "opt-in/opt-out com Safe Queue:",
                repr(exc)
            )

    return jsonify({
        "success": True,
        "lead_id": id,
        "opt_in": opt_in,
        "source": source_value,
        "opt_in_at": now_value,
        "opt_out": bool(opt_out_value)
    })


@app.route('/api/leads/<int:lead_id>/interacoes', methods=['POST'])
@login_required
def add_interacao(lead_id):
    data = request.json
    conn = get_db()
    conn.execute('''INSERT INTO interacoes (lead_id,tipo,descricao,usuario_id,agendamento,concluido)
        VALUES (?,?,?,?,?,?)''',
        (lead_id, data['tipo'], data['descricao'], session['user_id'],
         data.get('agendamento'), data.get('concluido', 1)))
    # Atualizar status do lead se necessário
    if data.get('novo_status'):
        conn.execute('UPDATE leads SET status=?,atualizado_em=CURRENT_TIMESTAMP WHERE id=?',
                     (_garantir_status_lead(conn, data['novo_status'])[0], lead_id))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# NEGÓCIOS
# ─────────────────────────────────────────────

@app.route('/api/negocios', methods=['GET', 'POST'])
@login_required
def negocios():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('''SELECT n.*, l.nome as lead_nome, l.telefone as lead_tel,
            e.nome as empreendimento FROM negocios n
            LEFT JOIN leads l ON n.lead_id=l.id
            LEFT JOIN empreendimentos e ON n.empreendimento_id=e.id
            ORDER BY n.criado_em DESC''').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json
    conn.execute('''INSERT INTO negocios
        (lead_id,empreendimento_id,tipo,status,valor_venda,valor_comissao,percentual_comissao,
         data_proposta,data_contrato,data_previsao_chaves,numero_contrato,unidade,bloco,andar,
         financiamento,banco_financiamento,valor_financiado,valor_entrada,observacoes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data['lead_id'], data.get('empreendimento_id'), data.get('tipo','Lancamento'),
         data.get('status','Proposta'), data.get('valor_venda',0),
         data.get('valor_comissao',0), data.get('percentual_comissao',0),
         data.get('data_proposta'), data.get('data_contrato'),
         data.get('data_previsao_chaves'), data.get('numero_contrato',''),
         data.get('unidade',''), data.get('bloco',''), data.get('andar'),
         data.get('financiamento',0), data.get('banco_financiamento',''),
         data.get('valor_financiado',0), data.get('valor_entrada',0),
         data.get('observacoes','')))
    negocio_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    # Criar comissão automaticamente
    if data.get('valor_comissao',0) > 0:
        conn.execute('''INSERT INTO comissoes (negocio_id,valor_total,status)
            VALUES (?,?,?)''', (negocio_id, data.get('valor_comissao',0), 'Pendente'))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': negocio_id})

@app.route('/api/negocios/<int:id>', methods=['GET', 'PUT'])
@login_required
def negocio_detail(id):
    conn = get_db()
    if request.method == 'GET':
        neg = conn.execute('''SELECT n.*, l.nome as lead_nome, l.telefone as lead_tel,
            l.email as lead_email, e.nome as empreendimento, c.nome as construtora
            FROM negocios n LEFT JOIN leads l ON n.lead_id=l.id
            LEFT JOIN empreendimentos e ON n.empreendimento_id=e.id
            LEFT JOIN construtoras c ON e.construtora_id=c.id
            WHERE n.id=?''', (id,)).fetchone()
        comissao = conn.execute('SELECT * FROM comissoes WHERE negocio_id=?', (id,)).fetchone()
        conn.close()
        return jsonify({'negocio': dict(neg) if neg else {}, 'comissao': dict(comissao) if comissao else {}})
    data = request.json
    conn.execute('''UPDATE negocios SET status=?,valor_venda=?,valor_comissao=?,
        percentual_comissao=?,data_proposta=?,data_contrato=?,data_previsao_chaves=?,
        data_entrega_chaves=?,numero_contrato=?,unidade=?,bloco=?,andar=?,
        financiamento=?,banco_financiamento=?,valor_financiado=?,valor_entrada=?,
        data_aprovacao_financiamento=?,observacoes=?,atualizado_em=CURRENT_TIMESTAMP WHERE id=?''',
        (data.get('status'), data.get('valor_venda',0), data.get('valor_comissao',0),
         data.get('percentual_comissao',0), data.get('data_proposta'),
         data.get('data_contrato'), data.get('data_previsao_chaves'),
         data.get('data_entrega_chaves'), data.get('numero_contrato',''),
         data.get('unidade',''), data.get('bloco',''), data.get('andar'),
         data.get('financiamento',0), data.get('banco_financiamento',''),
         data.get('valor_financiado',0), data.get('valor_entrada',0),
         data.get('data_aprovacao_financiamento'), data.get('observacoes',''), id))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# COMISSÕES
# ─────────────────────────────────────────────

@app.route('/api/comissoes', methods=['GET'])
@login_required
def comissoes():
    conn = get_db()
    rows = conn.execute('''SELECT cm.*, n.valor_venda, n.status as negocio_status,
        n.data_contrato, l.nome as lead_nome, e.nome as empreendimento
        FROM comissoes cm LEFT JOIN negocios n ON cm.negocio_id=n.id
        LEFT JOIN leads l ON n.lead_id=l.id
        LEFT JOIN empreendimentos e ON n.empreendimento_id=e.id
        ORDER BY cm.data_previsao''').fetchall()
    resumo = conn.execute('''SELECT
        COALESCE(SUM(valor_total),0) as total_previsto,
        COALESCE(SUM(valor_recebido),0) as total_recebido,
        COALESCE(SUM(CASE WHEN status="Pendente" THEN valor_total-valor_recebido ELSE 0 END),0) as a_receber
        FROM comissoes''').fetchone()
    conn.close()
    return jsonify({'comissoes': [dict(r) for r in rows], 'resumo': dict(resumo)})

@app.route('/api/comissoes/<int:id>', methods=['PUT'])
@login_required
def update_comissao(id):
    data = request.json
    conn = get_db()
    conn.execute('''UPDATE comissoes SET valor_recebido=?,status=?,
        data_previsao=?,data_recebimento=?,observacoes=? WHERE id=?''',
        (data.get('valor_recebido',0), data.get('status','Pendente'),
         data.get('data_previsao'), data.get('data_recebimento'),
         data.get('observacoes',''), id))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# TAREFAS
# ─────────────────────────────────────────────

@app.route('/api/tarefas', methods=['GET', 'POST'])
@login_required
def tarefas():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('''SELECT t.*, l.nome as lead_nome FROM tarefas t
            LEFT JOIN leads l ON t.lead_id=l.id
            ORDER BY t.data_vencimento ASC, t.prioridade DESC''').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json
    conn.execute('''INSERT INTO tarefas (titulo,descricao,lead_id,negocio_id,responsavel_id,
        data_vencimento,prioridade,status) VALUES (?,?,?,?,?,?,?,?)''',
        (data['titulo'], data.get('descricao',''), data.get('lead_id'),
         data.get('negocio_id'), session['user_id'],
         data.get('data_vencimento'), data.get('prioridade','Media'), 'Pendente'))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/tarefas/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def tarefa_detail(id):
    conn = get_db()
    if request.method == 'PUT':
        data = request.json
        conn.execute('UPDATE tarefas SET status=?,titulo=?,data_vencimento=? WHERE id=?',
                     (data.get('status'), data.get('titulo'), data.get('data_vencimento'), id))
        conn.commit(); conn.close()
        return jsonify({'success': True})
    conn.execute('DELETE FROM tarefas WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# WHATSAPP DISPARADOR
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# WHATSAPP — UPLOAD DE MÍDIA DA CAMPANHA
# ─────────────────────────────────────────────

@app.route(
    '/api/whatsapp/media',
    methods=['POST']
)
@login_required
def upload_whatsapp_media():

    uploaded = request.files.get("file")

    if not uploaded:
        return jsonify({
            "success": False,
            "error": "Nenhum arquivo enviado."
        }), 400

    original_name = (
        uploaded.filename
        or ""
    ).strip()

    if not original_name:
        return jsonify({
            "success": False,
            "error": "Nome do arquivo inválido."
        }), 400

    mimetype = (
        uploaded.mimetype
        or ""
    ).lower().strip()

    if mimetype in ALLOWED_MEDIA["image"]:

        media_type = "image"

    elif mimetype in ALLOWED_MEDIA["video"]:

        media_type = "video"

    else:

        return jsonify({
            "success": False,
            "error": (
                "Formato não suportado. "
                "Use JPG, PNG, WEBP ou MP4."
            )
        }), 400

    uploaded.stream.seek(
        0,
        os.SEEK_END
    )

    size = uploaded.stream.tell()

    uploaded.stream.seek(0)

    if size > MAX_MEDIA_SIZE:

        return jsonify({
            "success": False,
            "error": (
                "Arquivo muito grande. "
                "Limite: 64 MB."
            )
        }), 413

    safe_name = secure_filename(
        original_name
    )

    extension = (
        Path(safe_name).suffix.lower()
    )

    if not extension:

        extension = (
            ".jpg"
            if media_type == "image"
            else ".mp4"
        )

    stored_name = (
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )

    destination = (
        MEDIA_ROOT
        / stored_name
    )

    uploaded.save(
        destination
    )

    relative_path = str(
        destination.relative_to(
            MEDIA_ROOT
        )
    )

    return jsonify({
        "success": True,
        "media_type": media_type,
        "media_name": original_name,
        "media_mimetype": mimetype,
        "media_path": relative_path,
        "size": size,
    })


@app.route('/api/whatsapp/campanhas', methods=['GET', 'POST'])
@login_required
def campanhas_whatsapp():

    conn = get_db()

    try:

        if request.method == 'GET':

            _sincronizar_seguro(conn)

            rows = conn.execute(
                """
                SELECT *
                FROM mensagens_whatsapp
                ORDER BY criado_em DESC
                """
            ).fetchall()

            return jsonify([
                dict(row)
                for row in rows
            ])

        data = request.get_json(
            silent=True
        ) or {}

        nome_campanha = str(
            data.get(
                'nome_campanha',
                ''
            )
        ).strip()

        mensagem = str(
            data.get(
                'mensagem',
                ''
            )
        )

        contatos = data.get(
            'contatos',
            []
        )

        intervalo_segundos = data.get(
            'intervalo_segundos',
            8
        )

        if not nome_campanha:

            return jsonify({
                'success': False,
                'error': (
                    'nome_campanha é obrigatório'
                )
            }), 400

        if not isinstance(
            contatos,
            list
        ):

            return jsonify({
                'success': False,
                'error': (
                    'contatos deve ser uma lista'
                )
            }), 400

        try:

            intervalo_segundos = int(
                intervalo_segundos
            )

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                'success': False,
                'error': (
                    'intervalo_segundos inválido'
                )
            }), 400

        if intervalo_segundos < 0:

            return jsonify({
                'success': False,
                'error': (
                    'intervalo_segundos '
                    'não pode ser negativo'
                )
            }), 400

        midias_in = data.get('midias')
        if midias_in is None and data.get('media_path'):
            midias_in = [{
                'media_path': data.get('media_path'),
                'media_name': data.get('media_name'),
                'media_type': data.get('media_type'),
                'media_mimetype': data.get('media_mimetype'),
                'legenda': data.get('media_caption'),
            }]
        midias, erro_midia = _validar_midias(midias_in)
        if erro_midia:
            return jsonify({'success': False, 'error': erro_midia}), 400
        botoes_json, erro_botoes = _validar_botoes(data.get('botoes'), conn)
        if erro_botoes:
            return jsonify({'success': False, 'error': erro_botoes}), 400

        conn.execute(
            """
            INSERT INTO mensagens_whatsapp(
                nome_campanha,
                mensagem,
                lista_contatos,
                status,
                total_contatos,
                intervalo_segundos,
                botoes
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nome_campanha,
                mensagem,
                '',
                'Rascunho',
                len(contatos),
                intervalo_segundos,
                botoes_json
            )
        )

        campanha_id = (
            conn.execute(
                'SELECT last_insert_rowid()'
            )
            .fetchone()[0]
        )

        for contato in contatos:

            if not isinstance(
                contato,
                dict
            ):
                continue

            telefone = str(
                contato.get(
                    'telefone',
                    ''
                )
            ).strip()

            if not telefone:
                continue

            conn.execute(
                """
                INSERT INTO contatos_whatsapp(
                    campanha_id,
                    nome,
                    telefone
                )
                VALUES(?, ?, ?)
                """,
                (
                    campanha_id,
                    contato.get(
                        'nome',
                        ''
                    ),
                    telefone
                )
            )

        _salvar_midias(conn, campanha_id, midias)
        conn.commit()

        return jsonify({
            'success': True,
            'id': campanha_id,
            'status': 'Rascunho',
            'midias': len(midias),
            'media': {
                'path': midias[0]['media_path'],
                'name': midias[0]['media_name'],
                'type': midias[0]['media_type'],
                'mimetype': midias[0]['media_mimetype'],
                'caption': midias[0]['legenda'] or None,
            } if midias else None
        })

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


@app.route(
    '/api/whatsapp/campanhas/<int:id>/iniciar',
    methods=['POST']
)
@login_required
def iniciar_campanha(id):

    conn = get_db()

    try:

        campanha = conn.execute(
            """
            SELECT *
            FROM mensagens_whatsapp
            WHERE id=?
            """,
            (id,)
        ).fetchone()

        if not campanha:

            return jsonify({
                'success': False,
                'error': 'Campanha não encontrada'
            }), 404

        if campanha['status'] in {
            'Enviando',
            'Enfileirada'
        }:

            return jsonify({
                'success': False,
                'error': (
                    'Campanha já está '
                    'em processamento'
                )
            }), 409

        contatos = conn.execute(
            """
            SELECT *
            FROM contatos_whatsapp
            WHERE campanha_id=?
              AND status='Pendente'
            ORDER BY id
            """,
            (id,)
        ).fetchall()

        if not contatos:

            conn.execute(
                """
                UPDATE mensagens_whatsapp
                SET
                    status='Concluido',
                    iniciado_em=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (id,)
            )

            conn.commit()

            return jsonify({
                'success': True,
                'status': 'Concluido',
                'enfileirados': 0,
                'bloqueados': 0,
                'erros': 0,
                'message': (
                    'Nenhum contato pendente.'
                )
            })

        # Mapa dos leads autorizado pelo CRM.
        lead_rows = conn.execute(
            """
            SELECT
                nome,
                telefone,
                whatsapp_opt_in,
                whatsapp_opt_in_source,
                whatsapp_opt_in_at,
                whatsapp_opt_out,
                COALESCE(arquivado, 0) AS arquivado
            FROM leads
            WHERE telefone IS NOT NULL
              AND telefone <> ''
            """
        ).fetchall()

        lead_map = {}

        for lead in lead_rows:

            telefone = ''.join(
                ch
                for ch in str(
                    lead['telefone']
                )
                if ch.isdigit()
            )

            if telefone and not telefone.startswith(
                '55'
            ):

                telefone = (
                    '55'
                    + telefone
                )

            if telefone:

                lead_map[
                    telefone
                ] = lead

        midias = _midias_da_campanha(conn, campanha)
        botoes = _botoes_da_campanha(campanha)
        if not str(campanha['mensagem'] or '').strip() and not midias:
            return jsonify({'success': False, 'error': 'A campanha não tem mensagem nem mídia.'}), 400
        enfileirados = 0
        bloqueados = 0
        erros = 0

        for contato in contatos:

            telefone = ''.join(
                ch
                for ch in str(
                    contato['telefone']
                    or ''
                )
                if ch.isdigit()
            )

            if not telefone:

                conn.execute(
                    """
                    UPDATE contatos_whatsapp
                    SET
                        status=?,
                        erro_msg=?
                    WHERE id=?
                    """,
                    (
                        'Erro',
                        'Telefone inválido',
                        contato['id']
                    )
                )

                erros += 1
                continue

            if not telefone.startswith(
                '55'
            ):

                telefone = (
                    '55'
                    + telefone
                )

            lead = lead_map.get(
                telefone
            )

            if not lead:

                conn.execute(
                    """
                    UPDATE contatos_whatsapp
                    SET
                        status=?,
                        erro_msg=?
                    WHERE id=?
                    """,
                    (
                        'Bloqueado',
                        (
                            'Lead não localizado '
                            'no CRM'
                        ),
                        contato['id']
                    )
                )

                bloqueados += 1
                continue

            if lead['arquivado']:

                conn.execute(
                    "UPDATE contatos_whatsapp SET status=?, erro_msg=? WHERE id=?",
                    ('Bloqueado', 'Lead arquivado', contato['id'])
                )

                bloqueados += 1
                continue

            if (
                not lead['whatsapp_opt_in']
                or lead['whatsapp_opt_out']
            ):

                conn.execute(
                    """
                    UPDATE contatos_whatsapp
                    SET
                        status=?,
                        erro_msg=?
                    WHERE id=?
                    """,
                    (
                        'Bloqueado',
                        (
                            'Sem opt-in explícito '
                            'ou com opt-out'
                        ),
                        contato['id']
                    )
                )

                bloqueados += 1
                continue

            # Sincroniza o contato com a Safe Queue antes do enqueue.
            upsert_contact(
                phone=telefone,
                name=(
                    contato['nome']
                    or lead['nome']
                    or ''
                ),
                opt_in=True,
                opt_in_source=(
                    lead['whatsapp_opt_in_source']
                    or ''
                ),
                opt_in_at=(
                    lead['whatsapp_opt_in_at']
                ),
                opt_out=False
            )

            nome = str(
                contato['nome']
                or lead['nome']
                or ''
            )
            envios = _montar_envios(
                campanha,
                midias,
                botoes,
                nome
            )
            grupo = f"c{id}-k{contato['id']}-{uuid.uuid4().hex[:8]}"
            ids_fila = []
            erro_envio = None
            recusa = None
            try:
                for envio in envios:
                    m = envio['midia']
                    resultado = safe_enqueue(
                        phone=telefone,
                        message=envio['message'],
                        require_active=False,
                        send_mode='campaign',
                        media_path=m['media_path'] if m else None,
                        media_name=m['media_name'] if m else None,
                        media_type=m['media_type'] if m else None,
                        media_mimetype=m['media_mimetype'] if m else None,
                        media_caption=envio['caption'] if m else None,
                        group_key=grupo
                    )
                    if not resultado.get('accepted'):
                        recusa = resultado.get('reason', 'bloqueado')
                        break
                    ids_fila.append(resultado.get('queue_id'))
            except Exception as exc:
                erro_envio = str(exc)[:500]
            if erro_envio is not None or recusa is not None:
                if ids_fila:
                    cancel_pending(ids_fila)   # nao deixa envio parcial para tras
                conn.execute(
                    "UPDATE contatos_whatsapp SET status=?, erro_msg=? WHERE id=?",
                    (
                        'Erro' if erro_envio is not None else 'Bloqueado',
                        erro_envio if erro_envio is not None else recusa,
                        contato['id']
                    )
                )
                if erro_envio is not None:
                    erros += 1
                else:
                    bloqueados += 1
                continue
            conn.execute(
                "UPDATE contatos_whatsapp SET status=?, erro_msg=NULL, queue_id=? WHERE id=?",
                ('Enfileirado', ids_fila[0], contato['id'])
            )
            conn.execute("DELETE FROM contato_fila WHERE contato_id=?", (contato['id'],))
            for ordem, qid in enumerate(ids_fila, start=1):
                conn.execute(
                    "INSERT INTO contato_fila (contato_id, queue_id, ordem) VALUES (?,?,?)",
                    (contato['id'], qid, ordem)
                )
            enfileirados += 1

        novo_status = (
            'Enfileirada'
            if enfileirados
            else 'Concluido'
        )

        conn.execute(
            """
            UPDATE mensagens_whatsapp
            SET
                status=?,
                iniciado_em=CURRENT_TIMESTAMP,
                erros=?
            WHERE id=?
            """,
            (
                novo_status,
                bloqueados + erros,
                id
            )
        )

        conn.commit()

        return jsonify({
            'success': True,
            'status': novo_status,
            'enfileirados': enfileirados,
            'bloqueados': bloqueados,
            'erros': erros,
            'message': (
                'Campanha colocada '
                'na fila segura.'
            )
        })

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


_MAX_MIDIAS = 5
_MAX_BOTOES = 5
_ACOES_BOTAO = ('registrar', 'status', 'optout')
_CABECALHO_BOTOES = 'Responda com o número:'
_ACK_ENTREGUE = ('DELIVERY_ACK', 'DELIVERED', 'READ', 'PLAYED')


def _resolver_midia(media_path, media_type, media_mimetype):
    """Valida uma midia ja enviada ao servidor. Devolve (caminho_relativo, erro)."""
    media_path = str(media_path or '').strip()
    media_type = str(media_type or '').strip().lower()
    media_mimetype = str(media_mimetype or '').strip().lower()
    if not media_path:
        return None, 'media_path inválido'
    raiz = MEDIA_ROOT.resolve()
    recebido = Path(media_path)
    if recebido.is_absolute():
        caminho = recebido.resolve()
    else:
        caminho = (raiz / recebido).resolve()
        if not caminho.is_file():
            por_nome = (raiz / recebido.name).resolve()
            if por_nome.is_file():
                caminho = por_nome
    try:
        caminho.relative_to(raiz)
    except ValueError:
        return None, 'media_path inválido'
    if not caminho.is_file():
        return None, 'arquivo de mídia não encontrado'
    if media_type not in ALLOWED_MEDIA:
        return None, 'media_type inválido'
    if media_mimetype not in ALLOWED_MEDIA[media_type]:
        return None, 'media_mimetype incompatível com media_type'
    return str(caminho.relative_to(raiz)), None


def _validar_midias(lista):
    """Normaliza a lista de midias da campanha. Devolve (midias, erro)."""
    if lista is None:
        return [], None
    if not isinstance(lista, list):
        return None, 'midias deve ser uma lista'
    if len(lista) > _MAX_MIDIAS:
        return None, f'No máximo {_MAX_MIDIAS} mídias por campanha'
    saida = []
    for i, m in enumerate(lista, start=1):
        if not isinstance(m, dict):
            return None, f'Mídia {i}: formato inválido'
        rel, erro = _resolver_midia(m.get('media_path'), m.get('media_type'), m.get('media_mimetype'))
        if erro:
            return None, f'Mídia {i}: {erro}'
        legenda = m.get('legenda', m.get('media_caption'))
        saida.append({
            'media_path': rel,
            'media_name': str(m.get('media_name') or Path(rel).name)[:200],
            'media_type': str(m['media_type']).strip().lower(),
            'media_mimetype': str(m['media_mimetype']).strip().lower(),
            'legenda': str(legenda).strip()[:1024] if legenda else '',
        })
    return saida, None


def _validar_botoes(botoes, conn):
    """Valida os botoes de resposta rapida. Devolve (json | None, erro)."""
    if not botoes:
        return None, None
    if isinstance(botoes, list):
        botoes = {'itens': botoes}
    if not isinstance(botoes, dict):
        return None, 'botoes inválidos'
    itens_in = botoes.get('itens') or []
    if not itens_in:
        return None, None
    if len(itens_in) > _MAX_BOTOES:
        return None, f'No máximo {_MAX_BOTOES} botões'
    existentes = _status_existentes(conn)
    itens = []
    for i, b in enumerate(itens_in, start=1):
        b = b if isinstance(b, dict) else {}
        texto = ' '.join(str(b.get('texto') or '').split())[:60]
        if not texto:
            return None, f'Botão {i}: informe o texto'
        acao = str(b.get('acao') or 'registrar')
        if acao not in _ACOES_BOTAO:
            return None, f'Botão {i}: ação inválida'
        valor = ''
        if acao == 'status':
            chave = _token_texto(b.get('valor'))
            if chave not in existentes:
                return None, f'Botão {i}: escolha um status existente'
            valor = existentes[chave]
        itens.append({'texto': texto, 'acao': acao, 'valor': valor})
    cabecalho = ' '.join(str(botoes.get('cabecalho') or _CABECALHO_BOTOES).split())[:100]
    return json.dumps({'cabecalho': cabecalho, 'itens': itens}, ensure_ascii=False), None


def _botoes_da_campanha(campanha):
    try:
        bruto = campanha['botoes'] if 'botoes' in campanha.keys() else None
        dados = json.loads(bruto) if bruto else None
    except (ValueError, TypeError):
        dados = None
    return dados if isinstance(dados, dict) and dados.get('itens') else None


def _texto_botoes(botoes):
    if not botoes:
        return ''
    linhas = [botoes.get('cabecalho') or _CABECALHO_BOTOES]
    linhas += [f"{i}) {b['texto']}" for i, b in enumerate(botoes['itens'], start=1)]
    return '\n\n' + '\n'.join(linhas)


def _midias_da_campanha(conn, campanha):
    rows = conn.execute(
        "SELECT media_path, media_name, media_type, media_mimetype, legenda "
        "FROM campanha_midias WHERE campanha_id=? ORDER BY ordem, id",
        (campanha['id'],),
    ).fetchall()
    if rows:
        return [dict(r) for r in rows]
    if campanha['media_path']:   # campanhas antigas: uma midia nas colunas da propria campanha
        return [{
            'media_path': campanha['media_path'], 'media_name': campanha['media_name'],
            'media_type': campanha['media_type'], 'media_mimetype': campanha['media_mimetype'],
            'legenda': campanha['media_caption'] or '',
        }]
    return []


def _salvar_midias(conn, campanha_id, midias):
    conn.execute("DELETE FROM campanha_midias WHERE campanha_id=?", (campanha_id,))
    for ordem, m in enumerate(midias, start=1):
        conn.execute(
            "INSERT INTO campanha_midias (campanha_id, ordem, media_path, media_name, media_type, media_mimetype, legenda) "
            "VALUES (?,?,?,?,?,?,?)",
            (campanha_id, ordem, m['media_path'], m['media_name'], m['media_type'], m['media_mimetype'], m['legenda']),
        )
    p = midias[0] if midias else None   # a primeira midia tambem fica nas colunas antigas (compatibilidade)
    conn.execute(
        "UPDATE mensagens_whatsapp SET media_path=?, media_name=?, media_type=?, media_mimetype=?, media_caption=? WHERE id=?",
        (p['media_path'] if p else None, p['media_name'] if p else None, p['media_type'] if p else None,
         p['media_mimetype'] if p else None, (p['legenda'] or None) if p else None, campanha_id),
    )


def _montar_envios(campanha, midias, botoes, nome):
    """Sequencia de envios de UM contato.
    0 midia: texto (+ opcoes). 1 midia: legenda (ou o texto) + opcoes na propria midia.
    2+ midias: cada midia com sua legenda e, no fim, o texto (+ opcoes)."""
    msg = _aplicar_variaveis_mensagem(str(campanha['mensagem'] or ''), nome)
    opcoes = _texto_botoes(botoes)
    if not midias:
        return [{'message': (msg + opcoes).strip(), 'midia': None, 'caption': None}]
    if len(midias) == 1:
        m = midias[0]
        legenda = _aplicar_variaveis_mensagem(m['legenda'], nome) if m['legenda'] else ''
        corpo = ((legenda or msg) + opcoes).strip()
        return [{'message': corpo, 'midia': m, 'caption': corpo}]
    envios = []
    for m in midias:
        legenda = _aplicar_variaveis_mensagem(m['legenda'], nome) if m['legenda'] else ''
        envios.append({'message': legenda, 'midia': m, 'caption': legenda})
    final = (msg + opcoes).strip()
    if final:
        envios.append({'message': final, 'midia': None, 'caption': None})
    return envios


def _ids_fila_da_campanha(conn, campanha_id, status_contato=None):
    """Todos os itens da fila ligados aos contatos da campanha (um ou varios por contato)."""
    filtro, params = '', [campanha_id]
    if status_contato:
        filtro = ' AND ct.status IN (' + ','.join('?' * len(status_contato)) + ')'
        params += list(status_contato)
    ids = set()
    for r in conn.execute(
        'SELECT ct.queue_id AS q FROM contatos_whatsapp ct WHERE ct.campanha_id=? AND ct.queue_id IS NOT NULL' + filtro, params
    ).fetchall():
        ids.add(r['q'])
    for r in conn.execute(
        'SELECT cf.queue_id AS q FROM contato_fila cf JOIN contatos_whatsapp ct ON ct.id=cf.contato_id WHERE ct.campanha_id=?' + filtro, params
    ).fetchall():
        ids.add(r['q'])
    return sorted(ids)


def _fila_por_ids(ids):
    """{queue_id: linha} lendo a Safe Queue em blocos (limite de variaveis do SQLite)."""
    resultado = {}
    fila_conn = safe_queue_connect()
    try:
        ids = list(ids)
        for i in range(0, len(ids), 400):
            bloco = ids[i:i + 400]
            marcas = ",".join("?" * len(bloco))
            for r in fila_conn.execute(
                "SELECT id, status, delivery_status, error, reason, sent_at, evolution_message_id "
                "FROM queue WHERE id IN (" + marcas + ")", bloco,
            ).fetchall():
                resultado[r["id"]] = r
    finally:
        fila_conn.close()
    return resultado


def _sincronizar_status_campanhas(conn, campanha_id=None):
    """Reflete no CRM o que a Safe Queue ja fez (enviado, entregue, erro, bloqueio).
    Um contato pode ter varios itens na fila (varias midias + texto): o status e o conjunto deles.
    Simulacoes (DRY-RUN) nao contam como envio."""
    sql = (
        "SELECT id, campanha_id, queue_id FROM contatos_whatsapp "
        "WHERE status IN ('Enfileirado', 'Enviado') AND queue_id IS NOT NULL"
    )
    params = ()
    if campanha_id is not None:
        sql += " AND campanha_id=?"
        params = (campanha_id,)
    abertos = conn.execute(sql, params).fetchall()
    if not abertos:
        return 0

    por_contato = {a["id"]: [a["queue_id"]] for a in abertos}
    ids_contatos = list(por_contato)
    for i in range(0, len(ids_contatos), 400):
        bloco = ids_contatos[i:i + 400]
        marcas = ",".join("?" * len(bloco))
        for r in conn.execute(
            "SELECT contato_id, queue_id FROM contato_fila WHERE contato_id IN (" + marcas + ") ORDER BY ordem",
            bloco,
        ).fetchall():
            if r["queue_id"] not in por_contato[r["contato_id"]]:
                por_contato[r["contato_id"]].append(r["queue_id"])
    fila = _fila_por_ids({q for lista in por_contato.values() for q in lista})

    alterados = 0
    campanhas = set()
    for a in abertos:
        itens = [fila.get(q) for q in por_contato[a["id"]]]
        if any(i is None for i in itens):
            continue
        estados = [i["status"] for i in itens]
        erro = None
        enviado_em = None
        if "failed" in estados:
            novo = "Erro"
            erro = next(i["error"] for i in itens if i["status"] == "failed")
        elif "blocked" in estados:
            novo = "Bloqueado"
            erro = next(i["reason"] for i in itens if i["status"] == "blocked")
        elif all(e == "sent" for e in estados):
            if any(str(i["evolution_message_id"] or "").startswith("DRY-RUN") for i in itens):
                continue
            entregue = all(str(i["delivery_status"] or "").upper() in _ACK_ENTREGUE for i in itens)
            novo = "Entregue" if entregue else "Enviado"
            enviado_em = max((i["sent_at"] for i in itens if i["sent_at"]), default=None)
        else:
            continue
        cur = conn.execute(
            "UPDATE contatos_whatsapp SET status=?, erro_msg=?, "
            "enviado_em=COALESCE(enviado_em, ?) WHERE id=? AND status<>?",
            (novo, erro, enviado_em, a["id"], novo),
        )
        if cur.rowcount:
            alterados += 1
            campanhas.add(a["campanha_id"])

    for cid in campanhas:
        t = conn.execute(
            "SELECT "
            "COALESCE(SUM(status IN ('Enviado','Entregue')), 0) AS env, "
            "COALESCE(SUM(status IN ('Erro','Bloqueado')), 0) AS err, "
            "COALESCE(SUM(status IN ('Enfileirado','Pendente')), 0) AS aberto "
            "FROM contatos_whatsapp WHERE campanha_id=?",
            (cid,),
        ).fetchone()
        conn.execute(
            "UPDATE mensagens_whatsapp SET enviados=?, erros=?, "
            "status=CASE WHEN ?=0 THEN 'Concluido' ELSE status END, "
            "concluido_em=CASE WHEN ?=0 THEN COALESCE(concluido_em, CURRENT_TIMESTAMP) "
            "ELSE concluido_em END WHERE id=?",
            (t["env"], t["err"], t["aberto"], t["aberto"], cid),
        )
    conn.commit()
    return alterados


def _sincronizar_seguro(conn, campanha_id=None):
    """Nunca derruba a tela: se a fila estiver indisponivel, so avisa no log."""
    try:
        return _sincronizar_status_campanhas(conn, campanha_id)
    except Exception as exc:
        print("Aviso: falha ao sincronizar status com a Safe Queue:", exc)
        return 0


_VARIAVEL_NOME = _re.compile(
    r'\{\{?\s*(nome|primeiro_nome)\s*(?:\|\s*([^{}|]*?)\s*)?\}\}?',
    _re.IGNORECASE,
)
_PARTICULAS_NOME = {'da', 'de', 'do', 'das', 'dos', 'e'}


def _nome_amigavel(nome):
    """Nome pronto para mensagem: 'JOAO DA SILVA' ou 'joao da silva' viram 'Joao da Silva'."""
    nome = ' '.join(str(nome or '').split())
    if nome and (nome.isupper() or nome.islower()):
        partes = nome.split(' ')
        nome = ' '.join(
            p.lower() if (i and p.lower() in _PARTICULAS_NOME) else p.capitalize()
            for i, p in enumerate(partes)
        )
    return nome


def _aplicar_variaveis_mensagem(texto, nome):
    """Troca {nome}, {{nome}}, {primeiro_nome} e {nome|texto reserva} pelo nome do contato.
    Sem nome, usa o texto reserva (se houver) ou remove a variavel arrumando a pontuacao."""
    texto = str(texto or '')
    completo = _nome_amigavel(nome)
    primeiro = completo.split(' ')[0] if completo else ''
    ficou_vazio = False

    def trocar(m):
        nonlocal ficou_vazio
        valor = completo if m.group(1).lower() == 'nome' else primeiro
        if not valor:
            valor = (m.group(2) or '').strip()
        if not valor:
            ficou_vazio = True
        return valor

    resultado = _VARIAVEL_NOME.sub(trocar, texto)
    if ficou_vazio:
        resultado = _re.sub(r'[ \t]{2,}', ' ', resultado)
        resultado = _re.sub(r'[ \t]+([,.!?;:])', r'\1', resultado)
        resultado = _re.sub(r'([,;:])\s*\1', r'\1', resultado)
        resultado = _re.sub(r'([,;:])\s*([.!?])', r'\2', resultado)
    return resultado


@app.route('/api/whatsapp/previa', methods=['POST'])
@login_required
def previa_mensagem_whatsapp():
    data = request.get_json(silent=True) or {}
    return jsonify({
        'success': True,
        'texto': _aplicar_variaveis_mensagem(data.get('texto'), data.get('nome')),
    })


@app.route('/api/whatsapp/modelos', methods=['GET'])
@login_required
def listar_modelos_mensagem():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, nome, texto FROM modelos_mensagem ORDER BY nome COLLATE NOCASE"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route('/api/whatsapp/modelos', methods=['POST'])
@login_required
def salvar_modelo_mensagem():
    """Cria o modelo ou, se ja existir um com o mesmo nome, atualiza o texto."""
    data = request.get_json(silent=True) or {}
    nome = str(data.get('nome') or '').strip()
    texto = str(data.get('texto') or '').strip()
    if not nome or len(nome) > 100:
        return jsonify({'success': False, 'error': 'Informe um nome de até 100 caracteres.'}), 400
    if not texto or len(texto) > 4096:
        return jsonify({'success': False, 'error': 'A mensagem deve ter de 1 a 4096 caracteres.'}), 400
    conn = get_db()
    try:
        atual = conn.execute(
            "SELECT id FROM modelos_mensagem WHERE nome=?", (nome,)
        ).fetchone()
        if atual:
            conn.execute(
                "UPDATE modelos_mensagem SET texto=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=?",
                (texto, atual['id']),
            )
            conn.commit()
            return jsonify({'success': True, 'id': atual['id'], 'atualizado': True})
        cur = conn.execute(
            "INSERT INTO modelos_mensagem (nome, texto) VALUES (?, ?)", (nome, texto)
        )
        conn.commit()
        return jsonify({'success': True, 'id': cur.lastrowid, 'atualizado': False})
    finally:
        conn.close()


@app.route('/api/whatsapp/modelos/<int:id>', methods=['DELETE'])
@login_required
def excluir_modelo_mensagem(id):
    conn = get_db()
    try:
        n = conn.execute("DELETE FROM modelos_mensagem WHERE id=?", (id,)).rowcount
        conn.commit()
        if not n:
            return jsonify({'success': False, 'error': 'Modelo não encontrado'}), 404
        return jsonify({'success': True})
    finally:
        conn.close()


def _json_ou_none(texto):
    try:
        return json.loads(texto) if texto else None
    except (ValueError, TypeError):
        return None


def _registrar_edicao(camp, alteracoes):
    """Guarda o que mudou numa campanha ja enviada (auditoria). Mantem as 20 ultimas."""
    log = _json_ou_none(camp['edicoes_log'] if 'edicoes_log' in camp.keys() else None) or []
    log.append({'em': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'usuario_id': session.get('user_id'), 'alteracoes': alteracoes})
    return json.dumps(log[-20:], ensure_ascii=False)


@app.route('/api/whatsapp/campanhas/<int:id>', methods=['PUT'])
@login_required
def editar_campanha(id):
    """Edita a campanha.
    Rascunho: tudo (inclusive a lista de contatos).
    Ja iniciada/concluida: nome, mensagem, midias, botoes, intervalo e adicionar_contatos. O que
    foi enviado nao muda; as alteracoes valem para os proximos envios e ficam registradas.
    Enfileirada/Enviando: so o nome."""
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        camp = conn.execute("SELECT * FROM mensagens_whatsapp WHERE id=?", (id,)).fetchone()
        if not camp:
            return jsonify({'success': False, 'error': 'Campanha não encontrada'}), 404
        status = camp['status']
        so_conteudo = ('mensagem', 'midias', 'botoes', 'intervalo_segundos', 'contatos', 'adicionar_contatos')
        if status in ('Enfileirada', 'Enviando') and any(k in data for k in so_conteudo):
            return jsonify({'success': False, 'error': 'Campanha em envio: agora só o nome pode ser alterado.'}), 409
        if 'contatos' in data and status != 'Rascunho':
            return jsonify({'success': False, 'error': 'Campanha já iniciada: use adicionar_contatos para incluir novos contatos.'}), 409

        sets, params, alteracoes = [], [], {}
        if 'nome_campanha' in data:
            nome = str(data['nome_campanha'] or '').strip()
            if not nome:
                return jsonify({'success': False, 'error': 'Nome da campanha é obrigatório'}), 400
            if nome != camp['nome_campanha']:
                sets.append('nome_campanha=?'); params.append(nome[:200])
                alteracoes['nome_campanha'] = {'de': camp['nome_campanha'], 'para': nome[:200]}
        mensagem_final = str(camp['mensagem'] or '')
        if 'mensagem' in data:
            mensagem_final = str(data['mensagem'] or '').strip()
            if len(mensagem_final) > 4096:
                return jsonify({'success': False, 'error': 'A mensagem deve ter até 4096 caracteres.'}), 400
            if mensagem_final != (camp['mensagem'] or ''):
                sets.append('mensagem=?'); params.append(mensagem_final)
                alteracoes['mensagem'] = {'de': camp['mensagem'], 'para': mensagem_final}
        midias_atuais = _midias_da_campanha(conn, camp)
        midias_novas = None
        if 'midias' in data:
            midias_novas, erro = _validar_midias(data['midias'])
            if erro:
                return jsonify({'success': False, 'error': erro}), 400
            if [m['media_path'] + '|' + m['legenda'] for m in midias_novas] != [m['media_path'] + '|' + (m['legenda'] or '') for m in midias_atuais]:
                alteracoes['midias'] = {'de': [m['media_name'] for m in midias_atuais], 'para': [m['media_name'] for m in midias_novas]}
            else:
                midias_novas = None
        botoes_json = None
        if 'botoes' in data:
            botoes_json, erro = _validar_botoes(data['botoes'], conn)
            if erro:
                return jsonify({'success': False, 'error': erro}), 400
            if (botoes_json or '') != (camp['botoes'] or ''):
                sets.append('botoes=?'); params.append(botoes_json)
                alteracoes['botoes'] = {'de': _json_ou_none(camp['botoes']), 'para': _json_ou_none(botoes_json)}
        if 'intervalo_segundos' in data:
            try:
                intervalo = int(data['intervalo_segundos'])
            except (TypeError, ValueError):
                return jsonify({'success': False, 'error': 'intervalo_segundos inválido'}), 400
            if intervalo < 0:
                return jsonify({'success': False, 'error': 'intervalo_segundos não pode ser negativo'}), 400
            if intervalo != camp['intervalo_segundos']:
                sets.append('intervalo_segundos=?'); params.append(intervalo)
        total_midias = len(midias_novas) if midias_novas is not None else len(midias_atuais)
        if 'midias' in data and midias_novas is None:
            total_midias = len(midias_atuais)
        if not mensagem_final and not total_midias:
            return jsonify({'success': False, 'error': 'Informe uma mensagem ou ao menos uma mídia.'}), 400

        adicionados = 0
        existentes_tel = {
            _normalizar_telefone_br(r['telefone']) or r['telefone']
            for r in conn.execute("SELECT telefone FROM contatos_whatsapp WHERE campanha_id=?", (id,)).fetchall()
        }
        novos = []
        if 'contatos' in data:
            if not isinstance(data['contatos'], list) or not data['contatos']:
                return jsonify({'success': False, 'error': 'Adicione ao menos um contato.'}), 400
            existentes_tel = set()
            conn.execute("DELETE FROM contato_fila WHERE contato_id IN (SELECT id FROM contatos_whatsapp WHERE campanha_id=?)", (id,))
            conn.execute("DELETE FROM contatos_whatsapp WHERE campanha_id=?", (id,))
            novos = data['contatos']
            alteracoes['contatos'] = {'para': len(novos)}
        elif 'adicionar_contatos' in data:
            novos = data['adicionar_contatos'] if isinstance(data['adicionar_contatos'], list) else []
        for contato in novos:
            if not isinstance(contato, dict):
                continue
            tel = str(contato.get('telefone', '')).strip()
            chave = _normalizar_telefone_br(tel) or tel
            if not tel or chave in existentes_tel:
                continue
            existentes_tel.add(chave)
            conn.execute(
                "INSERT INTO contatos_whatsapp (campanha_id, nome, telefone) VALUES (?,?,?)",
                (id, str(contato.get('nome', ''))[:200], tel),
            )
            adicionados += 1
        if 'adicionar_contatos' in data:
            alteracoes['contatos_adicionados'] = adicionados

        if midias_novas is not None:
            _salvar_midias(conn, id, midias_novas)
        if adicionados or 'contatos' in data:
            total = conn.execute("SELECT COUNT(*) FROM contatos_whatsapp WHERE campanha_id=?", (id,)).fetchone()[0]
            sets.append('total_contatos=?'); params.append(total)
            if status in ('Concluido', 'Cancelado', 'Erro') and adicionados:
                sets.append("status='Rascunho'")   # Iniciar envia so os novos (Pendente)
        if status != 'Rascunho' and any(k in alteracoes for k in ('mensagem', 'midias', 'botoes')):
            sets.append('edicoes_log=?'); params.append(_registrar_edicao(camp, alteracoes))
        if sets:
            conn.execute('UPDATE mensagens_whatsapp SET ' + ', '.join(sets) + ' WHERE id=?', params + [id])
        conn.commit()
        novo_status = conn.execute("SELECT status FROM mensagens_whatsapp WHERE id=?", (id,)).fetchone()['status']
        return jsonify({'success': True, 'id': id, 'status': novo_status, 'alteracoes': list(alteracoes), 'contatos_adicionados': adicionados})
    finally:
        conn.close()


@app.route('/api/whatsapp/campanhas/<int:id>/duplicar', methods=['POST'])
@login_required
def duplicar_campanha(id):
    """Cria um novo rascunho com a lista de contatos da campanha (ex.: mensagem de 2o contato).
    contatos: todos | enviados | entregues | nao_responderam | erros"""
    data = request.get_json(silent=True) or {}
    filtros = {
        'todos': None,
        'enviados': ('Enviado', 'Entregue'),
        'entregues': ('Entregue',),
        'nao_responderam': ('Enviado', 'Entregue'),
        'erros': ('Erro', 'Bloqueado'),
    }
    quais = str(data.get('contatos') or 'todos')
    if quais not in filtros:
        return jsonify({'success': False, 'error': 'Filtro de contatos inválido.'}), 400
    conn = get_db()
    try:
        camp = conn.execute("SELECT * FROM mensagens_whatsapp WHERE id=?", (id,)).fetchone()
        if not camp:
            return jsonify({'success': False, 'error': 'Campanha não encontrada'}), 404
        _sincronizar_seguro(conn, id)
        sql = "SELECT nome, telefone, resposta FROM contatos_whatsapp WHERE campanha_id=?"
        params = [id]
        if filtros[quais]:
            sql += " AND status IN (" + ",".join("?" * len(filtros[quais])) + ")"
            params += list(filtros[quais])
        origem = conn.execute(sql + " ORDER BY id", params).fetchall()
        if quais == 'nao_responderam':
            origem = [r for r in origem if not (r['resposta'] or '').strip()]
        vistos, contatos = set(), []
        for r in origem:
            chave = _normalizar_telefone_br(r['telefone']) or r['telefone']
            if chave in vistos:
                continue
            vistos.add(chave)
            contatos.append(r)
        if not contatos:
            return jsonify({'success': False, 'error': 'Nenhum contato corresponde ao filtro escolhido.'}), 400
        nome = str(data.get('nome') or '').strip() or f"Cópia de {camp['nome_campanha']}"
        manter = lambda k: bool(data.get(k, True))
        cur = conn.execute(
            "INSERT INTO mensagens_whatsapp (nome_campanha, mensagem, lista_contatos, status, total_contatos, "
            "intervalo_segundos, botoes, duplicada_de) VALUES (?,?,?,?,?,?,?,?)",
            (nome[:200], (camp['mensagem'] or '') if manter('manter_mensagem') else '', '', 'Rascunho', len(contatos),
             camp['intervalo_segundos'], camp['botoes'] if manter('manter_botoes') else None, id),
        )
        novo_id = cur.lastrowid
        for r in contatos:
            conn.execute("INSERT INTO contatos_whatsapp (campanha_id, nome, telefone) VALUES (?,?,?)",
                         (novo_id, r['nome'], r['telefone']))
        if manter('manter_midias'):
            _salvar_midias(conn, novo_id, _midias_da_campanha(conn, camp))
        conn.commit()
        return jsonify({'success': True, 'id': novo_id, 'contatos': len(contatos), 'status': 'Rascunho'})
    finally:
        conn.close()


_RE_RESPOSTA_NUM = _re.compile('^\\s*([1-5])(?:\\ufe0f?\\u20e3)?\\s*[).:\\-]?\\s*$')


def _variantes_telefone(telefone):
    """O WhatsApp as vezes entrega o numero sem (ou com) o 9 apos o DDD."""
    d = _re.sub(r'\D', '', str(telefone or ''))
    variantes = {d}
    if len(d) == 12:
        variantes.add(d[:4] + '9' + d[4:])
    if len(d) == 13 and d[4] == '9':
        variantes.add(d[:4] + d[5:])
    return variantes


def _processar_resposta_rapida(conn, phone, texto, message_id=None):
    """Se `texto` for a resposta (numero ou texto do botao) a uma campanha com botoes enviada
    ao contato nos ultimos dias, registra a resposta e aplica a acao do botao."""
    texto = str(texto or '').strip()
    if not texto:
        return None
    if message_id:
        cur = conn.execute("INSERT OR IGNORE INTO respostas_processadas (message_id) VALUES (?)", (str(message_id),))
        if not cur.rowcount:
            return {'duplicada': True}
    variantes = _variantes_telefone(phone)
    limite = datetime.now() - timedelta(days=int(os.getenv('CRM_RESPOSTA_JANELA_DIAS', '7')))
    escolhido = None
    for r in conn.execute(
        "SELECT ct.id AS contato_id, ct.campanha_id, ct.telefone, ct.enviado_em, c.nome_campanha, c.botoes "
        "FROM contatos_whatsapp ct JOIN mensagens_whatsapp c ON c.id=ct.campanha_id "
        "WHERE c.botoes IS NOT NULL AND c.botoes<>'' AND ct.status IN ('Enviado','Entregue') "
        "ORDER BY ct.id DESC LIMIT 500"
    ).fetchall():
        if (_normalizar_telefone_br(r['telefone']) or '') not in variantes:
            continue
        if r['enviado_em']:
            try:
                enviado = datetime.fromisoformat(str(r['enviado_em']))
                if enviado.tzinfo:
                    enviado = enviado.astimezone().replace(tzinfo=None)
                if enviado < limite:
                    continue
            except ValueError:
                pass
        escolhido = r
        break
    if not escolhido:
        return None
    botoes = _json_ou_none(escolhido['botoes']) or {}
    itens = botoes.get('itens') or []
    m = _RE_RESPOSTA_NUM.match(texto)
    item = None
    if m and int(m.group(1)) <= len(itens):
        item = itens[int(m.group(1)) - 1]
    else:
        chave = _token_texto(texto)
        item = next((b for b in itens if _token_texto(b['texto']) == chave), None)
    if not item:
        return None
    conn.execute("UPDATE contatos_whatsapp SET resposta=?, respondido_em=CURRENT_TIMESTAMP WHERE id=?", (item['texto'], escolhido['contato_id']))
    aplicado = {'campanha_id': escolhido['campanha_id'], 'resposta': item['texto'], 'acao': item['acao'], 'leads': 0}
    leads = [
        l for l in conn.execute("SELECT id, nome, telefone FROM leads WHERE telefone IS NOT NULL AND telefone<>''").fetchall()
        if (_normalizar_telefone_br(l['telefone']) or '') in variantes
    ]
    for lead in leads:
        if item['acao'] == 'status':
            novo, _criado = _garantir_status_lead(conn, item['valor'])
            conn.execute("UPDATE leads SET status=?, atualizado_em=CURRENT_TIMESTAMP WHERE id=?", (novo, lead['id']))
        elif item['acao'] == 'optout':
            conn.execute(
                "UPDATE leads SET whatsapp_opt_in=0, whatsapp_opt_out=1, whatsapp_opt_in_source='', "
                "whatsapp_opt_in_at=NULL, atualizado_em=CURRENT_TIMESTAMP WHERE id=?", (lead['id'],))
            try:
                upsert_contact(phone=_normalizar_telefone_br(lead['telefone']), name=lead['nome'] or '', opt_in=False, opt_out=True)
            except Exception as exc:
                print('Aviso: não foi possível sincronizar o opt-out na Safe Queue:', exc)
        conn.execute(
            "INSERT INTO interacoes (lead_id, tipo, descricao, concluido) VALUES (?,?,?,1)",
            (lead['id'], 'WhatsApp', f"Resposta rápida: \u201c{item['texto']}\u201d (campanha {escolhido['nome_campanha']})"),
        )
        aplicado['leads'] += 1
    conn.commit()
    return aplicado


def _status_da_fila(queue_ids):
    """Status atual de cada item da Safe Queue: {queue_id: status}."""
    ids = [q for q in queue_ids if q]
    if not ids:
        return {}
    fila_conn = safe_queue_connect()
    try:
        marcas = ",".join("?" * len(ids))
        return {
            r["id"]: r["status"]
            for r in fila_conn.execute(
                "SELECT id, status FROM queue WHERE id IN (" + marcas + ")", ids
            ).fetchall()
        }
    finally:
        fila_conn.close()


@app.route('/api/whatsapp/safe/recuperar', methods=['POST'])
@login_required
def recuperar_itens_presos():
    """Trata itens presos em 'processing' (worker caiu). acao: 'requeue' ou 'fail'."""
    data = request.get_json(silent=True) or {}
    acao = str(data.get('acao', 'requeue'))
    if acao not in ('requeue', 'fail'):
        return jsonify({'success': False, 'error': "acao deve ser 'requeue' ou 'fail'"}), 400
    try:
        minutos = float(data.get('minutos', 10))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'minutos invalido'}), 400
    resultado = recover_stuck(older_than_minutes=minutos, action=acao)
    return jsonify({'success': True, **resultado})


@app.route('/api/whatsapp/campanhas/<int:id>', methods=['DELETE'])
@login_required
def excluir_campanha(id):
    """Exclui a campanha e seus contatos. Itens ainda pendentes na fila sao cancelados;
    o historico de envios ja feitos permanece na Safe Queue (auditoria)."""
    conn = get_db()
    try:
        camp = conn.execute(
            "SELECT id, status FROM mensagens_whatsapp WHERE id=?", (id,)
        ).fetchone()
        if not camp:
            return jsonify({'success': False, 'error': 'Campanha não encontrada'}), 404
        if camp['status'] == 'Enviando':
            return jsonify({'success': False, 'error': 'Campanha em envio. Aguarde terminar.'}), 409
        ids = _ids_fila_da_campanha(conn, id)
        if 'processing' in _status_da_fila(ids).values():
            return jsonify({
                'success': False,
                'error': 'Há envio em andamento nesta campanha. Aguarde ou use a recuperação de itens presos.',
            }), 409
        fila = cancel_pending(ids)
        conn.execute(
            "DELETE FROM contato_fila WHERE contato_id IN (SELECT id FROM contatos_whatsapp WHERE campanha_id=?)", (id,)
        )
        conn.execute("DELETE FROM campanha_midias WHERE campanha_id=?", (id,))
        removidos = conn.execute(
            "DELETE FROM contatos_whatsapp WHERE campanha_id=?", (id,)
        ).rowcount
        conn.execute("DELETE FROM mensagens_whatsapp WHERE id=?", (id,))
        conn.commit()
        return jsonify({
            'success': True,
            'contatos_removidos': removidos,
            'cancelados_na_fila': fila['cancelados'],
            'mantidos_no_historico': fila['ja_processados'],
        })
    finally:
        conn.close()


@app.route('/api/whatsapp/campanhas/<int:id>/reprocessar', methods=['POST'])
@login_required
def reprocessar_campanha(id):
    """Volta contatos com erro (e, se pedido, bloqueados) para 'Pendente' e reabre a campanha.
    Depois basta iniciar a campanha de novo: opt-in e opt-out sao reavaliados."""
    data = request.get_json(silent=True) or {}
    status_alvo = ['Erro'] + (['Bloqueado'] if data.get('incluir_bloqueados') else [])
    conn = get_db()
    try:
        camp = conn.execute(
            "SELECT id, status FROM mensagens_whatsapp WHERE id=?", (id,)
        ).fetchone()
        if not camp:
            return jsonify({'success': False, 'error': 'Campanha não encontrada'}), 404
        if camp['status'] == 'Enviando':
            return jsonify({'success': False, 'error': 'Campanha em envio.'}), 409
        _sincronizar_seguro(conn, id)
        abertos = _ids_fila_da_campanha(conn, id, ['Enfileirado'])
        if any(st in ('pending', 'processing') for st in _status_da_fila(abertos).values()):
            return jsonify({
                'success': False,
                'error': 'Ainda há itens desta campanha na fila. Aguarde o worker ou recupere os itens presos.',
            }), 409
        marcas = ",".join("?" * len(status_alvo))
        conn.execute(
            "DELETE FROM contato_fila WHERE contato_id IN (SELECT id FROM contatos_whatsapp "
            "WHERE campanha_id=? AND status IN (" + marcas + "))", [id] + status_alvo
        )
        n = conn.execute(
            "UPDATE contatos_whatsapp SET status='Pendente', erro_msg=NULL, queue_id=NULL "
            "WHERE campanha_id=? AND status IN (" + marcas + ")",
            [id] + status_alvo,
        ).rowcount
        if n:
            restantes = conn.execute(
                "SELECT COALESCE(SUM(status IN ('Erro','Bloqueado')), 0) FROM contatos_whatsapp WHERE campanha_id=?",
                (id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE mensagens_whatsapp SET status='Rascunho', erros=?, concluido_em=NULL WHERE id=?",
                (restantes, id),
            )
        conn.commit()
        return jsonify({'success': True, 'reprocessados': n, 'status_campanha': 'Rascunho' if n else camp['status']})
    finally:
        conn.close()


@app.route(
    '/api/whatsapp/campanhas/<int:id>',
    methods=['GET']
)
@login_required
def campanha_status(id):

    conn = get_db()

    try:

        _sincronizar_seguro(conn, id)

        camp = conn.execute(
            """
            SELECT *
            FROM mensagens_whatsapp
            WHERE id=?
            """,
            (id,)
        ).fetchone()

        contatos = conn.execute(
            """
            SELECT *
            FROM contatos_whatsapp
            WHERE campanha_id=?
            ORDER BY id
            """,
            (id,)
        ).fetchall()

        return jsonify({
            'campanha': (
                dict(camp)
                if camp
                else {}
            ),
            'midias': (
                _midias_da_campanha(conn, camp)
                if camp
                else []
            ),
            'botoes': (
                _botoes_da_campanha(camp)
                if camp
                else None
            ),
            'contatos': [
                dict(c)
                for c in contatos
            ]
        })

    finally:

        conn.close()


@app.route(
    '/api/whatsapp/template',
    methods=['POST']
)
@login_required
def whatsapp_template():

    data = request.get_json(
        silent=True
    ) or {}

    conn = get_db()

    try:

        filtros = []
        params = []

        if data.get('status'):

            filtros.append(
                'status=?'
            )

            params.append(
                data['status']
            )

        if data.get('temperatura'):

            filtros.append(
                'temperatura=?'
            )

            params.append(
                data['temperatura']
            )

        if data.get('tipo_interesse'):

            filtros.append(
                'tipo_interesse=?'
            )

            params.append(
                data['tipo_interesse']
            )

        where_parts = filtros + [
            'telefone != ""',
            'whatsapp_opt_in=1',
            'whatsapp_opt_out=0',
            'COALESCE(arquivado, 0)=0'
        ]

        where = (
            'WHERE '
            + ' AND '.join(
                where_parts
            )
        )

        leads_rows = conn.execute(
            f"""
            SELECT
                nome,
                telefone,
                whatsapp_opt_in,
                whatsapp_opt_in_source,
                whatsapp_opt_in_at,
                whatsapp_opt_out
            FROM leads
            {where}
            ORDER BY nome
            """,
            params
        ).fetchall()

        return jsonify([
            dict(row)
            for row in leads_rows
        ])

    finally:

        conn.close()


# ─────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────

@app.route('/api/configuracoes', methods=['GET', 'POST'])
@login_required
def configuracoes():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM configuracoes').fetchall()
        conn.close()
        return jsonify({r['chave']: r['valor'] for r in rows})
    data = request.json
    for chave, valor in data.items():
        conn.execute('INSERT OR REPLACE INTO configuracoes (chave,valor) VALUES (?,?)', (chave, valor))
    conn.commit(); conn.close()
    return jsonify({'success': True})

# ─────────────────────────────────────────────
# UNIDADES (tabelão)
# ─────────────────────────────────────────────

@app.route('/api/unidades', methods=['GET', 'POST'])
@login_required
def unidades():
    conn = get_db()
    if request.method == 'GET':
        empr_id = request.args.get('empreendimento_id')
        disp    = request.args.get('disponibilidade')
        filtros, params = [], []
        if empr_id:
            filtros.append('u.empreendimento_id=?'); params.append(empr_id)
        if disp:
            filtros.append('u.disponibilidade=?'); params.append(disp)
        where = ('WHERE ' + ' AND '.join(filtros)) if filtros else ''
        rows = conn.execute(f'''
            SELECT u.*, e.nome as empreendimento, c.nome as construtora
            FROM unidades u
            LEFT JOIN empreendimentos e ON u.empreendimento_id=e.id
            LEFT JOIN construtoras c ON e.construtora_id=c.id
            {where}
            ORDER BY u.empreendimento_id, u.bloco, u.andar, u.unidade
        ''', params).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    # POST — inserção individual
    d = request.json
    conn.execute('''INSERT INTO unidades
        (empreendimento_id,bloco,andar,unidade,tipologia,area_privativa,area_total,
         quartos,suites,banheiros,vagas,orientacao,valor_tabela,valor_desconto,
         percentual_desconto,disponibilidade,observacoes,fonte)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (d['empreendimento_id'], d.get('bloco',''), d.get('andar'),
         d['unidade'], d.get('tipologia',''), d.get('area_privativa'),
         d.get('area_total'), d.get('quartos'), d.get('suites'),
         d.get('banheiros'), d.get('vagas'), d.get('orientacao',''),
         d.get('valor_tabela'), d.get('valor_desconto'),
         d.get('percentual_desconto'), d.get('disponibilidade','Disponível'),
         d.get('observacoes',''), d.get('fonte','')))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/unidades/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def unidade_detail(id):
    conn = get_db()
    if request.method == 'PUT':
        d = request.json
        conn.execute('''UPDATE unidades SET disponibilidade=?,valor_tabela=?,valor_desconto=?,
            percentual_desconto=?,observacoes=?,data_reserva=? WHERE id=?''',
            (d.get('disponibilidade'), d.get('valor_tabela'), d.get('valor_desconto'),
             d.get('percentual_desconto'), d.get('observacoes'), d.get('data_reserva'), id))
        conn.commit(); conn.close()
        return jsonify({'success': True})
    conn.execute('DELETE FROM unidades WHERE id=?', (id,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/unidades/resumo/<int:empreendimento_id>')
@login_required
def unidades_resumo(empreendimento_id):
    conn = get_db()
    rows = conn.execute('''
        SELECT disponibilidade, COUNT(*) as total,
               COALESCE(MIN(valor_tabela),0) as valor_min,
               COALESCE(MAX(valor_tabela),0) as valor_max,
               COALESCE(AVG(valor_tabela),0) as valor_medio
        FROM unidades WHERE empreendimento_id=?
        GROUP BY disponibilidade
    ''', (empreendimento_id,)).fetchall()
    total = conn.execute(
        'SELECT COUNT(*) FROM unidades WHERE empreendimento_id=?',
        (empreendimento_id,)).fetchone()[0]
    conn.close()
    return jsonify({'resumo': [dict(r) for r in rows], 'total': total})

# ─────────────────────────────────────────────
# IMPORTAÇÃO EM MASSA (CSV / SQL inline)
# ─────────────────────────────────────────────

@app.route('/api/importar/unidades', methods=['POST'])
@login_required
def importar_unidades():
    """Recebe lista de unidades JSON e insere em lote."""
    data    = request.json
    linhas  = data.get('unidades', [])
    fonte   = data.get('fonte', 'importação manual')
    ok = erros = 0
    log = []
    conn = get_db()
    for i, u in enumerate(linhas, 1):
        try:
            if not u.get('empreendimento_id') or not u.get('unidade'):
                raise ValueError('empreendimento_id e unidade são obrigatórios')
            # calcula desconto automático se não veio
            vt = float(u.get('valor_tabela') or 0)
            vd = float(u.get('valor_desconto') or 0)
            perc = float(u.get('percentual_desconto') or 0)
            if vt and vd and not perc:
                perc = round((vt - vd) / vt * 100, 2)
            elif vt and perc and not vd:
                vd = round(vt * (1 - perc / 100), 2)
            conn.execute('''INSERT OR REPLACE INTO unidades
                (empreendimento_id,bloco,andar,unidade,tipologia,area_privativa,
                 area_total,quartos,suites,banheiros,vagas,orientacao,
                 valor_tabela,valor_desconto,percentual_desconto,
                 disponibilidade,observacoes,fonte)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (u['empreendimento_id'], u.get('bloco',''), u.get('andar'),
                 u['unidade'], u.get('tipologia',''), u.get('area_privativa'),
                 u.get('area_total'), u.get('quartos'), u.get('suites'),
                 u.get('banheiros'), u.get('vagas'), u.get('orientacao',''),
                 vt or None, vd or None, perc or None,
                 u.get('disponibilidade','Disponível'),
                 u.get('observacoes',''), fonte))
            ok += 1
        except Exception as e:
            erros += 1
            log.append(f'Linha {i}: {str(e)}')
    # Registra log
    conn.execute('''INSERT INTO importacoes
        (tipo,arquivo_nome,total_registros,importados,erros,log_detalhado)
        VALUES (?,?,?,?,?,?)''',
        ('tabela_valores', fonte, len(linhas), ok, erros,
         '\n'.join(log) if log else 'OK'))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'importados': ok, 'erros': erros, 'log': log})

@app.route('/api/importar/empreendimentos', methods=['POST'])
@login_required
def importar_empreendimentos():
    """Recebe lista de empreendimentos JSON (vinda do book) e insere em lote."""
    data   = request.json
    items  = data.get('empreendimentos', [])
    fonte  = data.get('fonte', 'importação book')
    ok = erros = 0
    log = []
    conn = get_db()
    for i, e in enumerate(items, 1):
        try:
            if not e.get('nome'):
                raise ValueError('nome é obrigatório')
            # Resolve construtora — cria se não existir
            c_id = e.get('construtora_id')
            if not c_id and e.get('construtora_nome'):
                row = conn.execute(
                    'SELECT id FROM construtoras WHERE nome=?',
                    (e['construtora_nome'],)).fetchone()
                if row:
                    c_id = row['id']
                else:
                    conn.execute(
                        'INSERT INTO construtoras (nome) VALUES (?)',
                        (e['construtora_nome'],))
                    c_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.execute('''INSERT INTO empreendimentos
                (construtora_id,nome,tipo,endereco,bairro,cidade,estado,cep,
                 valor_min,valor_max,area_min,area_max,quartos_min,quartos_max,
                 vagas_min,vagas_max,data_lancamento,data_entrega,status,
                 descricao,link_material,comissao_percentual)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (c_id, e['nome'], e.get('tipo','Apartamento'),
                 e.get('endereco',''), e.get('bairro',''), e.get('cidade',''),
                 e.get('estado','SP'), e.get('cep',''),
                 e.get('valor_min'), e.get('valor_max'),
                 e.get('area_min'), e.get('area_max'),
                 e.get('quartos_min'), e.get('quartos_max'),
                 e.get('vagas_min',0), e.get('vagas_max',2),
                 e.get('data_lancamento'), e.get('data_entrega'),
                 e.get('status','Em Lançamento'), e.get('descricao',''),
                 e.get('link_material',''), e.get('comissao_percentual',0.5)))
            ok += 1
        except Exception as ex:
            erros += 1
            log.append(f'Linha {i} ({e.get("nome","?")}): {str(ex)}')
    conn.execute('''INSERT INTO importacoes
        (tipo,arquivo_nome,total_registros,importados,erros,log_detalhado)
        VALUES (?,?,?,?,?,?)''',
        ('book', fonte, len(items), ok, erros,
         '\n'.join(log) if log else 'OK'))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'importados': ok, 'erros': erros, 'log': log})


_OPT_SIM = {'sim', 's', 'yes', 'y', 'true', '1', 'x', 'ok', 'autorizado', 'autorizou',
            'aceito', 'aceitou', 'consentiu', 'optin', 'opt-in', 'opt_in'}
_OPT_NAO = {'nao', 'n', 'no', 'false', '0', 'negado', 'recusou', 'recusado'}
_OPT_SAIR = {'optout', 'opt-out', 'opt_out', 'descadastrado', 'descadastrar',
             'bloqueado', 'remover', 'parar', 'stop', 'cancelar'}
_PRIORIDADE_DECISAO = {'sem_info': 0, 'nao': 1, 'optin': 2, 'optout': 3}


def _token_texto(valor):
    texto = _unicodedata.normalize('NFKD', str(valor or '')).encode('ascii', 'ignore').decode()
    return texto.strip().lower()


def _normalizar_telefone_br(valor):
    """Devolve o telefone no formato 55 + DDD + numero, ou None se invalido."""
    d = _re.sub(r'\D', '', str(valor or ''))
    if len(d) in (10, 11):
        d = '55' + d
    if len(d) not in (12, 13) or not d.startswith('55'):
        return None
    if int(d[2:4]) < 11:
        return None
    return d


def _parse_data_consentimento(valor):
    texto = str(valor or '').strip()
    for formato in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M:%S',
                    '%d/%m/%Y %H:%M', '%d/%m/%Y'):
        try:
            dt = datetime.strptime(texto, formato)
        except ValueError:
            continue
        if dt > datetime.now():
            return None
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return None


def _importar_leads_csv(conn, linhas, origem_padrao, opt_in_padrao, simular,
                        confirmo_base_legal, fonte, usuario_id, atualizar_status=False):
    """Cria/atualiza leads a partir de linhas de CSV, com registro de opt-in.

    Regras: opt-in so vale quando explicito (ou quando o usuario marcou o padrao do arquivo);
    opt-out sempre vence; opt-out existente nunca e revertido por CSV; origem do consentimento
    e obrigatoria para registrar opt-in. Com simular=True nada e gravado."""
    erros, avisos = [], []
    por_tel = {}
    for posicao, row in enumerate(linhas, start=1):
        if not isinstance(row, dict):
            continue
        linha = row.get('linha') or posicao
        tel = _normalizar_telefone_br(row.get('telefone'))
        if not tel:
            erros.append({'linha': linha, 'motivo': 'telefone invalido ou vazio'})
            continue
        t_in = _token_texto(row.get('opt_in'))
        t_out = _token_texto(row.get('opt_out'))
        if t_out in _OPT_SIM or t_out in _OPT_SAIR or t_in in _OPT_SAIR:
            decisao = 'optout'
        elif t_in in _OPT_SIM:
            decisao = 'optin'
        elif t_in in _OPT_NAO:
            decisao = 'nao'
        elif t_in == '':
            decisao = 'optin' if opt_in_padrao else 'sem_info'
        else:
            decisao = 'sem_info'
            avisos.append({'linha': linha, 'motivo': 'valor de opt-in nao reconhecido; tratado como sem opt-in'})
        if t_out not in ('',) and t_out not in _OPT_SIM and t_out not in _OPT_SAIR and t_out not in _OPT_NAO:
            avisos.append({'linha': linha, 'motivo': 'valor de opt-out nao reconhecido; ignorado'})
        email = str(row.get('email') or '').strip().lower()
        if email and '@' not in email:
            avisos.append({'linha': linha, 'motivo': 'e-mail invalido; ignorado'})
            email = ''
        entry = por_tel.setdefault(tel, {
            'nome': '', 'email': '', 'decisao': 'sem_info', 'origem': '',
            'data': None, 'linhas': [], 'conflito': False,
            'status': '', 'origem_lead': '', 'obs': '',
        })
        entry['linhas'].append(linha)
        if _limpar_status(row.get('status')):
            entry['status'] = _limpar_status(row.get('status'))
        if str(row.get('origem') or '').strip():
            entry['origem_lead'] = str(row['origem']).strip()[:100]
        if str(row.get('observacoes') or '').strip():
            entry['obs'] = str(row['observacoes']).strip()[:2000]
        if str(row.get('nome') or '').strip():
            entry['nome'] = str(row['nome']).strip()[:200]
        if email:
            entry['email'] = email[:200]
        if {entry['decisao'], decisao} >= {'optin', 'optout'}:
            entry['conflito'] = True
        if _PRIORIDADE_DECISAO[decisao] > _PRIORIDADE_DECISAO[entry['decisao']]:
            entry['decisao'] = decisao
            if decisao == 'optin':
                entry['origem'] = (str(row.get('origem_consentimento') or '').strip() or origem_padrao)[:200]
                entry['data'] = _parse_data_consentimento(row.get('data_consentimento'))
        elif decisao == 'optin' and entry['decisao'] == 'optin' and not entry['origem']:
            entry['origem'] = (str(row.get('origem_consentimento') or '').strip() or origem_padrao)[:200]
            entry['data'] = entry['data'] or _parse_data_consentimento(row.get('data_consentimento'))

    # opt-in sem origem do consentimento nao e importado
    for tel in list(por_tel):
        e = por_tel[tel]
        if e['decisao'] == 'optin' and not e['origem']:
            for linha in e['linhas']:
                erros.append({'linha': linha, 'motivo': 'opt-in sem origem do consentimento (informe a origem padrao)'})
            del por_tel[tel]

    tem_optin = any(e['decisao'] == 'optin' for e in por_tel.values())
    if tem_optin and not simular and not confirmo_base_legal:
        raise ValueError('Confirme que voce possui base legal para os contatos marcados como opt-in.')

    existentes = {}
    for lead in conn.execute(
        "SELECT id, nome, email, telefone, status, whatsapp_opt_in, whatsapp_opt_out, COALESCE(arquivado, 0) AS arquivado "
        "FROM leads WHERE telefone IS NOT NULL AND telefone<>''"
    ).fetchall():
        chave = _normalizar_telefone_br(lead['telefone'])
        if chave:
            existentes.setdefault(chave, []).append(dict(lead))

    r = {'criados': 0, 'leads_atualizados': 0, 'optin_registrados': 0, 'ja_tinham_optin': 0,
         'optin_ignorado_por_optout': 0, 'optout_registrados': 0, 'sem_alteracao_de_consentimento': 0,
         'conflitos_resolvidos_para_optout': 0, 'status_atualizados': 0, 'arquivados_encontrados': 0}
    # status da planilha que ainda nao existem no CRM sao acrescentados
    existentes_status = _status_existentes(conn)
    canon_status, novos_status = {}, []
    for e in por_tel.values():
        if not e['status']:
            continue
        chave = _token_texto(e['status'])
        if chave in existentes_status:
            canon_status[chave] = existentes_status[chave]
        elif chave not in canon_status:
            canon_status[chave] = e['status']
            novos_status.append(e['status'])
            if not simular:
                _garantir_status_lead(conn, e['status'], existentes_status)
    elegiveis, nao_elegiveis = [], 0
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for tel, e in por_tel.items():
        status_final = canon_status.get(_token_texto(e['status'])) if e['status'] else None
        origem_txt = f"CSV ({fonte}): {e['origem']}" if fonte else f"CSV: {e['origem']}"
        if e['conflito']:
            r['conflitos_resolvidos_para_optout'] += 1
        leads_do_tel = existentes.get(tel)
        if leads_do_tel:
            todos_elegiveis = True
            if any(l['arquivado'] for l in leads_do_tel):
                r['arquivados_encontrados'] += 1
                todos_elegiveis = False   # lead arquivado nao recebe campanha
            nome_final = e['nome'] or leads_do_tel[-1]['nome']
            for lead in leads_do_tel:
                sets, params = [], []
                if e['nome'] and e['nome'] != lead['nome']:
                    sets.append('nome=?'); params.append(e['nome'])
                if e['email'] and e['email'] != (lead['email'] or ''):
                    sets.append('email=?'); params.append(e['email'])
                if sets:
                    r['leads_atualizados'] += 1
                if atualizar_status and status_final and status_final != (lead['status'] or ''):
                    sets.append('status=?'); params.append(status_final)
                    r['status_atualizados'] += 1
                opt_in, opt_out = int(lead['whatsapp_opt_in'] or 0), int(lead['whatsapp_opt_out'] or 0)
                if e['decisao'] == 'optout':
                    if not (opt_out == 1 and opt_in == 0):
                        sets += ['whatsapp_opt_in=0', "whatsapp_opt_in_source=''", 'whatsapp_opt_in_at=NULL', 'whatsapp_opt_out=1']
                        r['optout_registrados'] += 1
                    opt_in, opt_out = 0, 1
                elif e['decisao'] == 'optin':
                    if opt_out == 1:
                        r['optin_ignorado_por_optout'] += 1
                    elif opt_in == 1:
                        r['ja_tinham_optin'] += 1
                    else:
                        sets += ['whatsapp_opt_in=1', 'whatsapp_opt_in_source=?', 'whatsapp_opt_in_at=?', 'whatsapp_opt_out=0']
                        params += [origem_txt, e['data'] or agora]
                        r['optin_registrados'] += 1
                        opt_in = 1
                else:
                    r['sem_alteracao_de_consentimento'] += 1
                if not (opt_in == 1 and opt_out == 0):
                    todos_elegiveis = False
                if sets and not simular:
                    conn.execute(
                        'UPDATE leads SET ' + ', '.join(sets) + ', atualizado_em=CURRENT_TIMESTAMP WHERE id=?',
                        params + [lead['id']],
                    )
            if todos_elegiveis:
                elegiveis.append({'nome': nome_final, 'telefone': tel})
            else:
                nao_elegiveis += 1
        else:
            r['criados'] += 1
            opt_in = 1 if e['decisao'] == 'optin' else 0
            opt_out = 1 if e['decisao'] == 'optout' else 0
            if opt_in:
                r['optin_registrados'] += 1
            if opt_out:
                r['optout_registrados'] += 1
            if not simular:
                conn.execute(
                    '''INSERT INTO leads
                       (nome, telefone, email, origem, tipo_interesse, status, temperatura, responsavel_id,
                        whatsapp_opt_in, whatsapp_opt_in_source, whatsapp_opt_in_at, whatsapp_opt_out, observacoes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (e['nome'] or f'Contato {tel[-4:]}', tel, e['email'], e['origem_lead'] or 'Importação CSV', 'Lancamento',
                     status_final or 'Novo', 'Frio', usuario_id, opt_in, origem_txt if opt_in else '',
                     (e['data'] or agora) if opt_in else None, opt_out, e['obs']),
                )
            if opt_in and not opt_out:
                elegiveis.append({'nome': e['nome'] or f'Contato {tel[-4:]}', 'telefone': tel})
            else:
                nao_elegiveis += 1

    duplicadas = sum(len(e['linhas']) - 1 for e in por_tel.values())
    relatorio = {
        'success': True, 'simulado': bool(simular), 'total_linhas': len(linhas),
        'telefones_unicos': len(por_tel), 'duplicadas_no_arquivo': duplicadas,
        **r, 'status_novos': novos_status, 'elegiveis': len(elegiveis), 'nao_elegiveis': nao_elegiveis,
        'erros_total': len(erros), 'erros': erros[:50], 'avisos_total': len(avisos), 'avisos': avisos[:50],
        'contatos_elegiveis': elegiveis,
    }
    if not simular:
        conn.execute(
            '''INSERT INTO importacoes (tipo, arquivo_nome, total_registros, importados, erros, log_detalhado)
               VALUES (?,?,?,?,?,?)''',
            ('leads_csv', fonte or 'csv', len(linhas), r['criados'] + r['leads_atualizados'], len(erros),
             json.dumps({k: v for k, v in relatorio.items() if k not in ('contatos_elegiveis', 'erros', 'avisos')}
                        | {'erros': erros[:200]}, ensure_ascii=False)),
        )
        conn.commit()
    return relatorio


@app.route('/api/importar/leads', methods=['POST'])
@login_required
def importar_leads_csv():
    data = request.get_json(silent=True) or {}
    linhas = data.get('linhas')
    if not isinstance(linhas, list) or not linhas:
        return jsonify({'success': False, 'error': 'Nenhuma linha para importar.'}), 400
    if len(linhas) > 20000:
        return jsonify({'success': False, 'error': 'Limite de 20.000 linhas por importação.'}), 400
    conn = get_db()
    try:
        relatorio = _importar_leads_csv(
            conn, linhas,
            origem_padrao=str(data.get('origem_padrao') or '').strip(),
            opt_in_padrao=bool(data.get('opt_in_padrao')),
            simular=bool(data.get('simular')),
            confirmo_base_legal=bool(data.get('confirmo_base_legal')),
            fonte=str(data.get('fonte') or '').strip()[:120],
            usuario_id=session.get('user_id'),
            atualizar_status=bool(data.get('atualizar_status')),
        )
        return jsonify(relatorio)
    except ValueError as exc:
        conn.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_PALETA_STATUS = ['#06b6d4', '#f97316', '#ec4899', '#84cc16', '#a855f7', '#14b8a6', '#eab308', '#f43f5e']


def _limpar_status(nome):
    return ' '.join(str(nome or '').split())[:40]


def _status_existentes(conn):
    """{nome sem acento/maiuscula: nome cadastrado} para casar 'visita' com 'Visita'."""
    return {_token_texto(r['nome']): r['nome'] for r in conn.execute("SELECT nome FROM status_leads")}


def _garantir_status_lead(conn, nome, existentes=None):
    """Devolve (nome_canonico, criado). Cria o status se ainda nao existir. Quem chama faz o commit."""
    nome = _limpar_status(nome)
    if not nome:
        return 'Novo', False
    existentes = existentes if existentes is not None else _status_existentes(conn)
    chave = _token_texto(nome)
    if chave in existentes:
        return existentes[chave], False
    proxima = (conn.execute("SELECT COALESCE(MAX(ordem), 0) FROM status_leads WHERE ordem < 9999").fetchone()[0] or 0) + 1
    qtd = conn.execute("SELECT COUNT(*) FROM status_leads").fetchone()[0]
    conn.execute(
        "INSERT INTO status_leads (nome, ordem, cor) VALUES (?, ?, ?)",
        (nome, proxima, _PALETA_STATUS[qtd % len(_PALETA_STATUS)]),
    )
    existentes[chave] = nome
    return nome, True


@app.route('/api/status-leads', methods=['GET'])
@login_required
def listar_status_leads():
    conn = get_db()
    try:
        rows = conn.execute("SELECT nome, ordem, cor FROM status_leads ORDER BY ordem, nome").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route('/api/status-leads', methods=['POST'])
@login_required
def criar_status_lead():
    nome = _limpar_status((request.get_json(silent=True) or {}).get('nome'))
    if not nome:
        return jsonify({'success': False, 'error': 'Informe o nome do status.'}), 400
    conn = get_db()
    try:
        canonico, criado = _garantir_status_lead(conn, nome)
        conn.commit()
        return jsonify({'success': True, 'nome': canonico, 'criado': criado})
    finally:
        conn.close()


_EXT_IMPORTACAO = {'.csv', '.txt', '.xlsx'}
_MAX_IMPORTACAO_BYTES = 10 * 1024 * 1024


def _xlsx_para_csv(origem):
    """Converte a primeira aba de uma planilha .xlsx em texto CSV (para o mesmo leitor do CSV)."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError('Suporte a .xlsx indisponível (instale openpyxl).') from exc
    wb = load_workbook(origem, read_only=True, data_only=True)
    try:
        saida = io.StringIO()
        escritor = csv.writer(saida)
        for linha in wb.worksheets[0].iter_rows(values_only=True):
            celulas = []
            for v in linha:
                if v is None:
                    celulas.append('')
                elif isinstance(v, float) and v.is_integer():
                    celulas.append(str(int(v)))
                elif isinstance(v, datetime):
                    celulas.append(v.strftime('%Y-%m-%d %H:%M:%S') if (v.hour or v.minute or v.second) else v.strftime('%Y-%m-%d'))
                elif isinstance(v, date):
                    celulas.append(v.strftime('%Y-%m-%d'))
                else:
                    celulas.append(str(v))
            if any(c.strip() for c in celulas):
                escritor.writerow(celulas)
        return saida.getvalue()
    finally:
        wb.close()


def _texto_do_arquivo(caminho):
    if caminho.suffix.lower() == '.xlsx':
        return _xlsx_para_csv(caminho)
    bruto = caminho.read_bytes()
    for codificacao in ('utf-8-sig', 'cp1252'):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode('latin-1')


@app.route('/api/importar/drive', methods=['GET'])
@login_required
def listar_arquivos_importacao():
    """Lista os arquivos da pasta de importacao (no Google Drive montado)."""
    try:
        CRM_IMPORT_ROOT.mkdir(parents=True, exist_ok=True)
        itens = []
        for p in CRM_IMPORT_ROOT.iterdir():
            if p.is_file() and not p.name.startswith(('.', '~$')) and p.suffix.lower() in _EXT_IMPORTACAO:
                st = p.stat()
                itens.append((st.st_mtime, {
                    'nome': p.name,
                    'tamanho_kb': round(st.st_size / 1024, 1),
                    'modificado': datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M'),
                }))
    except OSError as exc:
        return jsonify({'success': False, 'error': f'Não foi possível acessar a pasta de importação: {exc}'}), 503
    itens.sort(key=lambda t: t[0], reverse=True)
    return jsonify({'success': True, 'pasta': str(CRM_IMPORT_ROOT), 'arquivos': [i[1] for i in itens[:200]]})


@app.route('/api/importar/drive/ler', methods=['POST'])
@login_required
def ler_arquivo_importacao():
    nome = str((request.get_json(silent=True) or {}).get('arquivo') or '')
    if not nome or nome != os.path.basename(nome) or '\\' in nome or nome.startswith('.'):
        return jsonify({'success': False, 'error': 'Nome de arquivo inválido.'}), 400
    if Path(nome).suffix.lower() not in _EXT_IMPORTACAO:
        return jsonify({'success': False, 'error': 'Use arquivos .csv, .txt ou .xlsx.'}), 400
    try:
        real = (CRM_IMPORT_ROOT / nome).resolve(strict=True)
    except (FileNotFoundError, OSError):
        return jsonify({'success': False, 'error': 'Arquivo não encontrado na pasta de importação.'}), 404
    # precisa estar DIRETAMENTE dentro da pasta (bloqueia atalhos/links para fora dela)
    if real.parent != CRM_IMPORT_ROOT.resolve() or not real.is_file():
        return jsonify({'success': False, 'error': 'Arquivo fora da pasta de importação.'}), 400
    if real.stat().st_size > _MAX_IMPORTACAO_BYTES:
        return jsonify({'success': False, 'error': 'Arquivo maior que 10 MB.'}), 413
    try:
        texto = _texto_do_arquivo(real)
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 501
    except Exception:
        return jsonify({'success': False, 'error': 'Não foi possível ler o arquivo. Confira se não está corrompido.'}), 422
    return jsonify({'success': True, 'nome': nome, 'texto': texto})


@app.route('/api/importar/converter', methods=['POST'])
@login_required
def converter_planilha_xlsx():
    """Recebe um .xlsx enviado do computador e devolve o texto CSV da primeira aba."""
    arquivo = request.files.get('arquivo')
    if not arquivo or Path(arquivo.filename or '').suffix.lower() != '.xlsx':
        return jsonify({'success': False, 'error': 'Envie um arquivo .xlsx.'}), 400
    bruto = arquivo.read(_MAX_IMPORTACAO_BYTES + 1)
    if len(bruto) > _MAX_IMPORTACAO_BYTES:
        return jsonify({'success': False, 'error': 'Arquivo maior que 10 MB.'}), 413
    try:
        return jsonify({'success': True, 'texto': _xlsx_para_csv(io.BytesIO(bruto))})
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 501
    except Exception:
        return jsonify({'success': False, 'error': 'Não foi possível ler a planilha.'}), 422


@app.route('/api/importacoes', methods=['GET'])
@login_required
def historico_importacoes():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM importacoes ORDER BY criado_em DESC LIMIT 50'
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─────────────────────────────────────────────
# WHATSAPP WEBHOOK / SAFE MODE
# ─────────────────────────────────────────────

def _extract_whatsapp_message(payload):
    """
    Extrai mensagens individuais da Evolution API.

    Normaliza o nome do evento porque a Evolution pode
    entregar o payload como "messages.upsert", enquanto
    a configuração utiliza "MESSAGES_UPSERT".
    """

    event = str(
        payload.get("event", "")
    ).strip().upper().replace(".", "_").replace("-", "_")

    if event and event != "MESSAGES_UPSERT":
        return None

    data = payload.get("data") or {}
    key = data.get("key") or {}

    # Ignora mensagens enviadas pelo próprio número
    if key.get("fromMe", False):
        return None

    remote_jid = str(
        key.get("remoteJid") or ""
    ).strip()

    remote_jid_alt = str(
        key.get("remoteJidAlt") or ""
    ).strip()

    # Ignora grupos
    if "@g.us" in remote_jid:
        return None

    # Descobrir telefone
    candidates = [
        remote_jid,
        remote_jid_alt,
        str(key.get("participantAlt") or "").strip(),
        str(key.get("participant") or "").strip(),
    ]

    phone = ""

    for candidate in candidates:

        if not candidate:
            continue

        # JID tradicional
        if "@s.whatsapp.net" in candidate:
            phone = candidate.split("@", 1)[0]
            break

        # Número puro
        digits = "".join(
            ch for ch in candidate
            if ch.isdigit()
        )

        # Não considerar LID como telefone
        if "@lid" not in candidate and len(digits) >= 10:
            phone = digits
            break

    if not phone:
        return None

    push_name = (
        data.get("pushName")
        or data.get("notifyName")
        or ""
    )

    message = data.get("message") or {}

    text = (
        message.get("conversation")
        or message.get("extendedTextMessage", {}).get("text")
        or message.get("imageMessage", {}).get("caption")
        or message.get("videoMessage", {}).get("caption")
        or ""
    )

    return {
        "phone": phone,
        "name": str(push_name),
        "text": str(text)[:5000],
    }


@app.route('/api/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """
    Endpoint público chamado pela Evolution API.
    """

    payload = request.get_json(silent=True) or {}

    try:

        event = str(
            payload.get("event", "")
        ).strip().upper().replace(".", "_").replace("-", "_")

        # ─────────────────────────────────────
        # MESSAGES_UPDATE
        # ─────────────────────────────────────

        if event == "MESSAGES_UPDATE":

            data = payload.get("data") or {}

            evolution_message_id = (
                data.get("keyId")
                or data.get("id")
            )

            status = data.get("status")

            updated = update_message_status(
                evolution_message_id,
                status
            )

            _conn_sync = get_db()
            try:
                _sincronizar_seguro(_conn_sync)
            finally:
                _conn_sync.close()

            return jsonify({
                "ok": True,
                "event": "MESSAGES_UPDATE",
                "updated": updated,
                "message_id": evolution_message_id,
                "status": status,
            })

        # ─────────────────────────────────────
        # MESSAGES_UPSERT
        # ─────────────────────────────────────

        extracted = _extract_whatsapp_message(
            payload
        )

        if extracted is None:
            return jsonify({
                "ok": True,
                "ignored": True
            })

        phone = extracted["phone"]
        name = extracted["name"]
        text = extracted["text"]

        register_incoming(
            phone=phone,
            name=name,
            detail=text,
        )

        resposta_rapida = None
        try:
            _conn_resp = get_db()
            try:
                resposta_rapida = _processar_resposta_rapida(
                    _conn_resp,
                    phone,
                    text,
                    ((payload.get("data") or {}).get("key") or {}).get("id")
                    if isinstance(payload, dict) else None,
                )
            finally:
                _conn_resp.close()
        except Exception as exc:
            print("Aviso: falha ao processar resposta rápida:", repr(exc))

        return jsonify({
            "ok": True,
            "received": True,
            "phone": phone,
            "resposta_rapida": resposta_rapida,
        })

    except Exception as exc:

        print(
            "❌ Erro no webhook WhatsApp:",
            repr(exc)
        )

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@app.route('/api/whatsapp/safe/dashboard', methods=['GET'])
def whatsapp_safe_dashboard():
    return jsonify(
        safe_dashboard_data()
    )


@app.route('/api/whatsapp/safe/queue', methods=['GET'])
def whatsapp_safe_queue():
    limit = request.args.get(
        'limit',
        default=100,
        type=int
    )

    limit = min(
        max(limit, 1),
        500
    )

    return jsonify(
        safe_queue_list(limit)
    )

# ─────────────────────────────────────────────
# PROXY DA EVOLUTION API
# ─────────────────────────────────────────────

EVOLUTION_LOCAL_URL = os.getenv(
    "EVOLUTION_LOCAL_URL",
    "http://127.0.0.1:8081"
)


@app.route('/evolution/<path:path>', methods=[
    'GET', 'POST', 'PUT', 'DELETE', 'PATCH'
])
def evolution_proxy(path):
    """
    Proxy simples do CRM para a Evolution API local.
    Mantém a Evolution fora da Internet e usa o único
    endpoint público do ngrok para os dois serviços.
    """

    target_url = f"{EVOLUTION_LOCAL_URL.rstrip('/')}/{path}"

    try:
        response = requests.request(
            method=request.method,
            url=target_url,
            headers={
                key: value
                for key, value in request.headers
                if key.lower() not in {
                    'host',
                    'content-length'
                }
            },
            params=request.args,
            data=request.get_data(),
            timeout=30,
        )

        excluded_headers = {
            'content-encoding',
            'content-length',
            'transfer-encoding',
            'connection',
        }

        response_headers = [
            (key, value)
            for key, value in response.headers.items()
            if key.lower() not in excluded_headers
        ]

        return (
            response.content,
            response.status_code,
            response_headers
        )

    except requests.RequestException as exc:
        return jsonify({
            "ok": False,
            "error": "Falha ao acessar Evolution API",
            "detail": str(exc),
        }), 502

# ─────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────

@app.route('/')
@app.route('/<path:path>')
def index(path=''):
    return render_template('index.html')

if __name__ == '__main__':
    init_db()
    print("\n🏠 CRM Imobiliário iniciado!")
    print("📌 Acesse: http://localhost:5000")
    app.run(debug=os.getenv('CRM_DEBUG', '0') == '1', host='0.0.0.0', port=5000, use_reloader=False)
