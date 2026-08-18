"""
ImobiCRM Pro — Popular dados de demonstração
Execute: python seed_demo.py
"""
import sqlite3, hashlib, random
from datetime import datetime, timedelta
from app import init_db, DB_PATH

CONSTRUTORAS = [
    ('MRV Engenharia', '08.343.592/0001-20', 'Carlos Mendes', '(11) 3004-5050', 'crm@mrv.com.br', 'mrv.com.br'),
    ('Cyrela', '73.182.924/0001-21', 'Ana Paula', '(11) 3018-8000', 'vendas@cyrela.com.br', 'cyrela.com.br'),
    ('EZTec', '62.019.862/0001-30', 'Ricardo Lima', '(11) 3372-6300', 'contato@eztec.com.br', 'eztec.com.br'),
    ('Plano&Plano', '06.205.009/0001-17', 'Fernanda Costa', '(11) 3004-2900', 'atendimento@planoplano.com.br', 'planoplano.com.br'),
    ('Direcional', '16.614.075/0001-00', 'Marcos Alves', '(11) 3003-1234', 'vendas@direcional.com.br', 'direcional.com.br'),
]

EMPREENDIMENTOS = [
    ('Parque Vista Verde', 1, 'Apartamento', 'Av. das Nações, 1200', 'Penha', 'São Paulo', 'SP', 380000, 620000, 48, 92, 2, 3, '2024-03-15', '2026-06-01', 'Em Lançamento', 0.5),
    ('Residencial Monet', 2, 'Apartamento', 'R. das Artes, 450', 'Vila Mariana', 'São Paulo', 'SP', 650000, 1200000, 65, 140, 2, 4, '2024-01-10', '2026-12-01', 'Em Lançamento', 0.6),
    ('Studio 25 Pinheiros', 3, 'Studio', 'R. Teodoro Sampaio, 880', 'Pinheiros', 'São Paulo', 'SP', 280000, 380000, 25, 35, 1, 1, '2023-09-01', '2025-08-01', 'Em Obras', 0.5),
    ('Gran Reserva Alphaville', 4, 'Casa', 'Al. Rio Negro, 500', 'Alphaville', 'Barueri', 'SP', 900000, 2500000, 180, 320, 3, 5, '2024-05-20', '2027-03-01', 'Em Lançamento', 0.7),
    ('Solar das Palmeiras', 1, 'Apartamento', 'R. Vergueiro, 2300', 'Saúde', 'São Paulo', 'SP', 420000, 780000, 55, 98, 2, 3, '2023-06-01', '2025-10-01', 'Em Obras', 0.5),
    ('Vertical Business', 5, 'Comercial', 'Av. Paulista, 1754', 'Bela Vista', 'São Paulo', 'SP', 320000, 850000, 30, 90, 0, 1, '2024-02-01', '2026-04-01', 'Em Lançamento', 0.4),
]

NOMES = ['João Silva','Maria Santos','Pedro Oliveira','Ana Costa','Lucas Ferreira',
         'Carla Mendes','Roberto Alves','Fernanda Lima','Carlos Eduardo','Patrícia Souza',
         'Rafael Martins','Juliana Pereira','André Moreira','Camila Rodrigues','Bruno Nascimento',
         'Letícia Cardoso','Thiago Barbosa','Mariana Ribeiro','Felipe Gomes','Amanda Araújo',
         'Marcos Vieira','Priscila Castro','Rodrigo Freitas','Daniela Lopes','Gabriel Rocha']

ORIGENS = ['Instagram','Facebook','Google','Indicação','Portal ImóvelWeb','ZAP Imóveis',
           'Viva Real','QuintoAndar','Plantão','Site','Direto']

INTERACOES = [
    'Ligação de boas-vindas realizada. Cliente demonstrou interesse.',
    'Enviou documentação por WhatsApp.',
    'Visita ao stand de vendas agendada para próxima semana.',
    'Aprovado para financiamento CEF.',
    'Solicitou planta baixa do apartamento tipo.',
    'Cliente comparou com empreendimento concorrente.',
    'Proposta enviada por email.',
    'Retornou ligação, pediu mais informações sobre o andar.',
    'Visita realizada ao apartamento decorado.',
    'Aguardando aprovação do crédito no banco.',
]

def random_tel():
    ddd = random.choice(['11','12','13','14','15','16','17','18','19'])
    return f'({ddd}) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}'

def random_email(nome):
    n = nome.lower().replace(' ','.')
    d = random.choice(['gmail.com','hotmail.com','yahoo.com.br','outlook.com'])
    return f'{n}@{d}'

def random_date(start_days_ago=180, end_days_ago=0):
    delta = random.randint(end_days_ago, start_days_ago)
    return (datetime.now() - timedelta(days=delta)).strftime('%Y-%m-%d')

def seed():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print('🌱 Populando dados de demonstração...')

    # Construtoras
    for nome, cnpj, contato, tel, email, site in CONSTRUTORAS:
        c.execute('''INSERT OR IGNORE INTO construtoras
            (nome,cnpj,contato_nome,contato_telefone,contato_email,site)
            VALUES (?,?,?,?,?,?)''', (nome, cnpj, contato, tel, email, site))
    conn.commit()
    print(f'  ✅ {len(CONSTRUTORAS)} construtoras criadas')

    # Empreendimentos
    for nome, cid, tipo, end, bairro, cidade, estado, vmin, vmax, amin, amax, qmin, qmax, dlanc, dent, status, comissao in EMPREENDIMENTOS:
        c.execute('''INSERT OR IGNORE INTO empreendimentos
            (construtora_id,nome,tipo,endereco,bairro,cidade,estado,valor_min,valor_max,
             area_min,area_max,quartos_min,quartos_max,data_lancamento,data_entrega,status,comissao_percentual)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (cid, nome, tipo, end, bairro, cidade, estado, vmin, vmax, amin, amax, qmin, qmax, dlanc, dent, status, comissao))
    conn.commit()
    print(f'  ✅ {len(EMPREENDIMENTOS)} empreendimentos criados')

    # Leads
    emprs = c.execute('SELECT id FROM empreendimentos').fetchall()
    empr_ids = [e[0] for e in emprs]
    lead_ids = []
    statuses = ['Novo','Novo','Contato','Contato','Visita','Proposta','Contrato','Fechado','Perdido']
    temperaturas = ['Frio','Frio','Morno','Morno','Quente']
    tipos = ['Lancamento','Lancamento','Lancamento','QuintoAndar']

    for nome in NOMES:
        status = random.choice(statuses)
        tipo = random.choice(tipos)
        temp = random.choice(temperaturas)
        empr_id = random.choice(empr_ids) if tipo == 'Lancamento' else None
        data = random_date(120, 0)
        c.execute('''INSERT INTO leads
            (nome,telefone,email,origem,tipo_interesse,empreendimento_id,status,temperatura,
             valor_interesse,responsavel_id,criado_em,atualizado_em)
            VALUES (?,?,?,?,?,?,?,?,?,1,?,?)''',
            (nome, random_tel(), random_email(nome), random.choice(ORIGENS),
             tipo, empr_id, status, temp,
             random.choice([380000,450000,520000,680000,750000,900000]),
             data, data))
        lead_ids.append(c.lastrowid)

    conn.commit()
    print(f'  ✅ {len(NOMES)} leads criados')

    # Interações
    for lead_id in lead_ids:
        num = random.randint(0, 3)
        tipos_int = ['Ligação','Email','Nota','Visita','Agendamento']
        for _ in range(num):
            data = random_date(90, 0)
            c.execute('''INSERT INTO interacoes (lead_id,tipo,descricao,usuario_id,data_hora)
                VALUES (?,?,?,1,?)''',
                (lead_id, random.choice(tipos_int), random.choice(INTERACOES), data))
    conn.commit()

    # Negócios para leads "Contrato" e "Fechado"
    negocios_leads = c.execute(
        'SELECT id, empreendimento_id FROM leads WHERE status IN ("Contrato","Fechado")'
    ).fetchall()

    for lead_id, empr_id in negocios_leads:
        valor = random.choice([450000, 520000, 620000, 720000, 850000, 980000])
        perc = random.choice([0.5, 0.6, 0.7])
        comissao = valor * perc / 100
        status_neg = 'Fechado' if random.random() > 0.3 else 'Contrato'
        data_c = random_date(60, 10)
        unidade = f'{random.randint(1,20)}{random.randint(1,4):02d}'
        bloco = random.choice(['A','B','C','D'])
        c.execute('''INSERT INTO negocios
            (lead_id,empreendimento_id,tipo,status,valor_venda,percentual_comissao,valor_comissao,
             unidade,bloco,andar,data_proposta,data_contrato,data_previsao_chaves,financiamento)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (lead_id, empr_id or random.choice(empr_ids), 'Lancamento', status_neg,
             valor, perc, comissao, unidade, bloco, random.randint(1,20),
             random_date(70,15), data_c if status_neg=='Fechado' else None,
             '2026-12-01', random.choice([0,0,1])))
        neg_id = c.lastrowid
        # Comissão
        status_com = 'Pago' if status_neg=='Fechado' and random.random()>0.5 else ('Parcial' if status_neg=='Fechado' else 'Pendente')
        c.execute('''INSERT INTO comissoes (negocio_id,valor_total,valor_recebido,status)
            VALUES (?,?,?,?)''',
            (neg_id, comissao, comissao if status_com=='Pago' else (comissao/2 if status_com=='Parcial' else 0), status_com))

    conn.commit()
    print(f'  ✅ {len(negocios_leads)} negócios + comissões criados')

    # Tarefas
    tarefas = [
        ('Ligar para João Silva', 'Alta', 0),
        ('Enviar material do Parque Vista Verde', 'Alta', 1),
        ('Agendar visita ao stand', 'Media', 2),
        ('Follow-up proposta Cyrela', 'Alta', -1),
        ('Verificar documentação financiamento', 'Media', 3),
        ('Enviar planta baixa por WhatsApp', 'Baixa', 5),
        ('Reunião com equipe de vendas MRV', 'Media', 7),
        ('Atualizar planilha de leads', 'Baixa', 0),
    ]
    for titulo, prior, dias in tarefas:
        data = datetime.now() + timedelta(days=dias)
        c.execute('''INSERT INTO tarefas (titulo,responsavel_id,data_vencimento,prioridade,status)
            VALUES (?,1,?,?,"Pendente")''', (titulo, data.strftime('%Y-%m-%d %H:%M'), prior))

    conn.commit()
    print(f'  ✅ {len(tarefas)} tarefas criadas')

    conn.close()
    print('\n🎉 Dados de demonstração inseridos com sucesso!')
    print('   Acesse o CRM e veja o dashboard populado.')

if __name__ == '__main__':
    seed()
