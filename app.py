from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS
import sqlite3
import json
import os
import hashlib
import uuid
from datetime import datetime, timedelta
import requests
import time
import threading
from urllib.parse import urljoin

# ─────────────────────────────────────────────
# WHATSAPP / SAFE QUEUE
# ─────────────────────────────────────────────

from whatsapp.safe_queue import (
    register_incoming,
    upsert_contact,
    dashboard as safe_dashboard_data,
    list_queue as safe_queue_list,
    enqueue as safe_enqueue,
)

app = Flask(__name__)
app.secret_key = 'crm_imobiliario_secret_2024'
CORS(app)

DB_PATH = 'database/crm.db'

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs('database', exist_ok=True)
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
        c.execute('INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)', (k, v))

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
        'leads_total': conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0],
        'leads_mes': conn.execute('SELECT COUNT(*) FROM leads WHERE criado_em >= ?', (mes_inicio,)).fetchone()[0],
        'leads_novos': conn.execute('SELECT COUNT(*) FROM leads WHERE status="Novo"').fetchone()[0],
        'negocios_abertos': conn.execute('SELECT COUNT(*) FROM negocios WHERE status NOT IN ("Fechado","Cancelado")').fetchone()[0],
        'negocios_fechados_mes': conn.execute('SELECT COUNT(*) FROM negocios WHERE status="Fechado" AND data_contrato >= ?', (mes_inicio,)).fetchone()[0],
        'vgv_mes': conn.execute('SELECT COALESCE(SUM(valor_venda),0) FROM negocios WHERE status="Fechado" AND data_contrato >= ?', (mes_inicio,)).fetchone()[0],
        'comissao_mes': conn.execute('SELECT COALESCE(SUM(valor_comissao),0) FROM negocios WHERE status="Fechado" AND data_contrato >= ?', (mes_inicio,)).fetchone()[0],
        'tarefas_hoje': conn.execute('SELECT COUNT(*) FROM tarefas WHERE DATE(data_vencimento)=? AND status="Pendente"', (hoje,)).fetchone()[0],
        'tarefas_atrasadas': conn.execute('SELECT COUNT(*) FROM tarefas WHERE DATE(data_vencimento)<? AND status="Pendente"', (hoje,)).fetchone()[0],
    }

    # Funil de leads
    funil = conn.execute('''SELECT status, COUNT(*) as total FROM leads GROUP BY status ORDER BY
        CASE status WHEN "Novo" THEN 1 WHEN "Contato" THEN 2 WHEN "Visita" THEN 3
        WHEN "Proposta" THEN 4 WHEN "Contrato" THEN 5 WHEN "Fechado" THEN 6 ELSE 7 END''').fetchall()

    # Leads por origem
    origens = conn.execute('SELECT origem, COUNT(*) as total FROM leads GROUP BY origem ORDER BY total DESC LIMIT 6').fetchall()

    # Últimos leads
    ultimos_leads = conn.execute('''SELECT l.*, e.nome as empreendimento FROM leads l
        LEFT JOIN empreendimentos e ON l.empreendimento_id=e.id
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
         data.get('empreendimento_id'), data.get('status','Novo'),
         data.get('temperatura','Frio'), data.get('valor_interesse'),
         data.get('observacoes',''), data.get('utm_source',''),
         data.get('utm_medium',''), data.get('utm_campaign',''),
         session['user_id']))
    conn.commit(); conn.close()
    return jsonify({'success': True})

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
             data.get('empreendimento_id'), data.get('status','Novo'),
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
                     (data['novo_status'], lead_id))
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

@app.route('/api/whatsapp/campanhas', methods=['GET', 'POST'])
@login_required
def campanhas_whatsapp():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM mensagens_whatsapp ORDER BY criado_em DESC').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.json
    contatos = data.get('contatos', [])
    conn.execute('''INSERT INTO mensagens_whatsapp
        (nome_campanha,mensagem,status,total_contatos,intervalo_segundos)
        VALUES (?,?,?,?,?)''',
        (data['nome_campanha'], data['mensagem'], 'Rascunho',
         len(contatos), data.get('intervalo_segundos', 5)))
    campanha_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    for contato in contatos:
        conn.execute('''INSERT INTO contatos_whatsapp (campanha_id,nome,telefone)
            VALUES (?,?,?)''', (campanha_id, contato.get('nome',''), contato['telefone']))
    conn.commit(); conn.close()
    return jsonify({'success': True, 'id': campanha_id})

@app.route('/api/whatsapp/campanhas/<int:id>/iniciar', methods=['POST'])
@login_required
def iniciar_campanha(id):
    conn = get_db()
    campanha = conn.execute('SELECT * FROM mensagens_whatsapp WHERE id=?', (id,)).fetchone()
    if not campanha:
        conn.close()
        return jsonify({'error': 'Campanha não encontrada'}), 404
    config = conn.execute('SELECT * FROM configuracoes WHERE chave IN ("whatsapp_api_url","whatsapp_token")').fetchall()
    configs = {r['chave']: r['valor'] for r in config}
    conn.execute('UPDATE mensagens_whatsapp SET status="Enviando",iniciado_em=CURRENT_TIMESTAMP WHERE id=?', (id,))
    conn.commit()
    contatos = conn.execute('SELECT * FROM contatos_whatsapp WHERE campanha_id=? AND status="Pendente"', (id,)).fetchall()
    conn.close()

    def enviar_em_background():
        enviados = 0
        erros = 0
        for contato in contatos:
            try:
                telefone = ''.join(filter(str.isdigit, contato['telefone']))
                if not telefone.startswith('55'):
                    telefone = '55' + telefone
                mensagem = campanha['mensagem']
                # Personalização de variáveis
                if contato['nome']:
                    mensagem = mensagem.replace('{{nome}}', contato['nome'])

                # Chamada à API do WhatsApp (Evolution API / WPPConnect)
                api_url = configs.get('whatsapp_api_url', '')
                token = configs.get('whatsapp_token', '')
                sucesso = False

                if api_url and token:
                    try:
                        resp = requests.post(
                            f"{api_url}/message/sendText/default",
                            headers={'apikey': token, 'Content-Type': 'application/json'},
                            json={'number': telefone, 'text': mensagem},
                            timeout=10
                        )
                        sucesso = resp.status_code in [200, 201]
                    except:
                        sucesso = False
                else:
                    # Modo simulação (sem API configurada)
                    sucesso = True
                    time.sleep(0.5)

                db = get_db()
                if sucesso:
                    db.execute('''UPDATE contatos_whatsapp SET status="Enviado",
                        enviado_em=CURRENT_TIMESTAMP WHERE id=?''', (contato['id'],))
                    enviados += 1
                else:
                    db.execute('''UPDATE contatos_whatsapp SET status="Erro",
                        erro_msg="Falha no envio" WHERE id=?''', (contato['id'],))
                    erros += 1
                db.execute('''UPDATE mensagens_whatsapp SET enviados=?,erros=? WHERE id=?''',
                           (enviados, erros, id))
                db.commit(); db.close()
                time.sleep(campanha['intervalo_segundos'])
            except Exception as e:
                erros += 1

        db = get_db()
        db.execute('''UPDATE mensagens_whatsapp SET status="Concluido",
            concluido_em=CURRENT_TIMESTAMP WHERE id=?''', (id,))
        db.commit(); db.close()

    thread = threading.Thread(target=enviar_em_background, daemon=True)
    thread.start()
    return jsonify({'success': True, 'message': 'Campanha iniciada!'})

@app.route('/api/whatsapp/campanhas/<int:id>', methods=['GET'])
@login_required
def campanha_status(id):
    conn = get_db()
    camp = conn.execute('SELECT * FROM mensagens_whatsapp WHERE id=?', (id,)).fetchone()
    contatos = conn.execute('SELECT * FROM contatos_whatsapp WHERE campanha_id=? ORDER BY id', (id,)).fetchall()
    conn.close()
    return jsonify({'campanha': dict(camp) if camp else {}, 'contatos': [dict(c) for c in contatos]})

@app.route('/api/whatsapp/template', methods=['POST'])
@login_required
def whatsapp_template():
    """Gera lista de contatos a partir de filtros de leads"""
    data = request.json
    conn = get_db()
    filtros = []
    params = []
    if data.get('status'):
        filtros.append('status=?'); params.append(data['status'])
    if data.get('temperatura'):
        filtros.append('temperatura=?'); params.append(data['temperatura'])
    if data.get('tipo_interesse'):
        filtros.append('tipo_interesse=?'); params.append(data['tipo_interesse'])
    where = ('WHERE ' + ' AND '.join(filtros) + ' AND telefone != ""') if filtros else 'WHERE telefone != ""'
    leads = conn.execute(f'SELECT nome, telefone FROM leads {where}', params).fetchall()
    conn.close()
    return jsonify([dict(l) for l in leads])

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
    Extrai mensagens individuais da Evolution API,
    incluindo casos de endereçamento LID.
    """

    event = str(payload.get("event", "")).upper()

    if event and event != "MESSAGES_UPSERT":
        return None

    data = payload.get("data") or {}
    key = data.get("key") or {}

    # Ignora mensagens enviadas pelo próprio número
    if key.get("fromMe", False):
        return None

    remote_jid = key.get("remoteJid") or ""
    remote_jid_alt = key.get("remoteJidAlt") or ""

    # ---------------------------------------------------------
    # GRUPOS
    # ---------------------------------------------------------

    if "@g.us" in remote_jid:
        return None

    # ---------------------------------------------------------
    # DESCOBRIR O TELEFONE REAL
    # ---------------------------------------------------------

    candidates = [
        remote_jid,
        remote_jid_alt,
        key.get("participantAlt") or "",
        key.get("participant") or "",
    ]

    phone = ""

    for candidate in candidates:
        candidate = str(candidate).strip()

        if not candidate:
            continue

        # Número clássico
        if "@s.whatsapp.net" in candidate:
            phone = candidate.split("@")[0]
            break

        # Número puro
        digits = "".join(ch for ch in candidate if ch.isdigit())

        # LIDs numéricos não devem ser usados como telefone
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
        "name": push_name,
        "text": str(text)[:5000],
    }

@app.route('/api/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """
    Endpoint público chamado pela Evolution API.
    """

    payload = request.get_json(silent=True) or {}

    try:
        extracted = _extract_whatsapp_message(payload)

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
            text=text,
        )

        return jsonify({
            "ok": True,
            "received": True,
            "phone": phone,
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
    print("👤 Login: admin@crm.com | Senha: admin123\n")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
