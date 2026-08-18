import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, init_db

@pytest.fixture
def client(tmp_path):
    """Cria um cliente de teste com banco temporário."""
    import app as app_module
    app_module.DB_PATH = str(tmp_path / 'test_crm.db')
    os.makedirs(str(tmp_path), exist_ok=True)
    init_db()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test_secret'
    with app.test_client() as c:
        yield c

def login(client):
    return client.post('/api/login',
        json={'email': 'admin@crm.com', 'senha': 'admin123'},
        content_type='application/json')

def test_login_sucesso(client):
    r = login(client)
    data = r.get_json()
    assert r.status_code == 200
    assert data['success'] is True

def test_login_falha(client):
    r = client.post('/api/login',
        json={'email': 'nao@existe.com', 'senha': 'errada'},
        content_type='application/json')
    assert r.status_code == 401

def test_me_sem_login(client):
    r = client.get('/api/me')
    data = r.get_json()
    assert data['logado'] is False

def test_me_com_login(client):
    login(client)
    r = client.get('/api/me')
    data = r.get_json()
    assert data['logado'] is True

def test_criar_construtora(client):
    login(client)
    r = client.post('/api/construtoras',
        json={'nome': 'Construtora Teste LTDA', 'cnpj': '00.000.000/0001-00'},
        content_type='application/json')
    assert r.get_json()['success'] is True

def test_listar_construtoras(client):
    login(client)
    client.post('/api/construtoras', json={'nome': 'ABC Incorporações'},
                content_type='application/json')
    r = client.get('/api/construtoras')
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1

def test_criar_lead(client):
    login(client)
    r = client.post('/api/leads',
        json={'nome': 'João da Silva', 'telefone': '11999990000', 'origem': 'Instagram'},
        content_type='application/json')
    assert r.get_json()['success'] is True

def test_listar_leads(client):
    login(client)
    client.post('/api/leads', json={'nome': 'Maria Santos'},
                content_type='application/json')
    r = client.get('/api/leads')
    data = r.get_json()
    assert len(data) >= 1

def test_dashboard(client):
    login(client)
    r = client.get('/api/dashboard')
    data = r.get_json()
    assert 'stats' in data
    assert 'funil' in data
    assert data['stats']['leads_total'] >= 0

def test_criar_empreendimento(client):
    login(client)
    r = client.post('/api/empreendimentos',
        json={'nome': 'Torre Alpha', 'tipo': 'Apartamento', 'cidade': 'São Paulo'},
        content_type='application/json')
    assert r.get_json()['success'] is True

def test_criar_negocio(client):
    login(client)
    client.post('/api/leads', json={'nome': 'Carlos Corretor'},
                content_type='application/json')
    leads = client.get('/api/leads').get_json()
    lead_id = leads[0]['id']
    r = client.post('/api/negocios',
        json={'lead_id': lead_id, 'valor_venda': 500000, 'percentual_comissao': 0.5,
              'valor_comissao': 2500, 'status': 'Proposta'},
        content_type='application/json')
    assert r.get_json()['success'] is True

def test_autenticacao_protegida(client):
    """Rotas protegidas retornam 401 sem login."""
    r = client.get('/api/leads')
    assert r.status_code == 401
