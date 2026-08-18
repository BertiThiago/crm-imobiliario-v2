#!/usr/bin/env python3
"""
ImobiCRM Pro — Processador de Books e Tabelões
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Lê PDFs, imagens, Excel e CSV de construtoras e gera:
  • empreendimentos_import.csv  + empreendimentos_import.sql
  • unidades_import.csv         + unidades_import.sql
  • relatorio_extracao.txt

Uso:
    python processar_arquivos.py                     # modo interativo
    python processar_arquivos.py --arquivo book.pdf  # arquivo direto
    python processar_arquivos.py --pasta ./arquivos  # pasta inteira
"""

import os, sys, re, csv, json, argparse, textwrap
from datetime import datetime
from pathlib import Path

# ── Dependências opcionais (instala automaticamente se faltar) ─────────────
def instalar(pkg, import_as=None):
    import importlib, subprocess
    nome = import_as or pkg.split('[')[0].replace('-','_')
    try:
        return importlib.import_module(nome)
    except ImportError:
        print(f"  📦 Instalando {pkg}...")
        subprocess.run([sys.executable,'-m','pip','install',pkg,
                        '--break-system-packages','-q'], check=True)
        return importlib.import_module(nome)

# ─────────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path('importacao_output')
OUTPUT_DIR.mkdir(exist_ok=True)

TS = datetime.now().strftime('%Y%m%d_%H%M%S')

# ══════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS DE LIMPEZA
# ══════════════════════════════════════════════════════════════════════════

def limpar_valor(txt):
    """'R$ 450.000,00' → 450000.0"""
    if not txt:
        return None
    txt = str(txt)
    txt = re.sub(r'[R$\s]', '', txt)
    txt = txt.replace('.', '').replace(',', '.')
    try:
        return float(txt)
    except:
        return None

def limpar_area(txt):
    """'87,50 m²' → 87.5"""
    if not txt:
        return None
    txt = re.sub(r'[m²\s]', '', str(txt)).replace(',', '.')
    try:
        return float(txt)
    except:
        return None

def limpar_int(txt):
    if not txt:
        return None
    m = re.search(r'\d+', str(txt))
    return int(m.group()) if m else None

def limpar_data(txt):
    """Várias formatos → YYYY-MM-DD ou None"""
    if not txt:
        return None
    txt = str(txt).strip()
    for fmt in ('%d/%m/%Y','%m/%Y','%Y-%m-%d','%d-%m-%Y','%Y'):
        try:
            dt = datetime.strptime(txt, fmt)
            return dt.strftime('%Y-%m-%d')
        except:
            pass
    # "1º trimestre 2026" → 2026-03-31
    m = re.search(r'(\d{4})', txt)
    if m:
        return f"{m.group(1)}-12-31"
    return None

def inferir_tipologia(row_dict):
    """Tenta montar tipologia legível a partir de campos dispersos."""
    q = row_dict.get('quartos') or row_dict.get('dormitorios') or row_dict.get('dorms')
    s = row_dict.get('suites') or row_dict.get('suite')
    v = row_dict.get('vagas') or row_dict.get('garagem')
    a = row_dict.get('area_privativa') or row_dict.get('area') or row_dict.get('área')
    partes = []
    if q:
        partes.append(f"{q} dorms")
    if s and str(s) not in ('0','None',''):
        partes.append(f"{s} suíte{'s' if int(str(s).split('.')[0])>1 else ''}")
    if v:
        partes.append(f"{v} vaga{'s' if int(str(v).split('.')[0])>1 else ''}")
    if a:
        partes.append(f"{a}m²")
    return ' · '.join(partes) if partes else ''

def normalizar_disponibilidade(txt):
    if not txt:
        return 'Disponível'
    txt = str(txt).upper().strip()
    if any(x in txt for x in ['DISP','LIVRE','FREE','AVAIL']):
        return 'Disponível'
    if any(x in txt for x in ['RESERV','BLOQ','HOLD']):
        return 'Reservado'
    if any(x in txt for x in ['VEND','SOLD','NEGOC']):
        return 'Vendido'
    return 'Disponível'

# ══════════════════════════════════════════════════════════════════════════
# LEITORES POR TIPO DE ARQUIVO
# ══════════════════════════════════════════════════════════════════════════

class ResultadoExtracao:
    def __init__(self, arquivo):
        self.arquivo       = arquivo
        self.empreendimentos = []   # lista de dicts
        self.unidades        = []   # lista de dicts
        self.avisos          = []
        self.erros           = []

    def ok(self):
        return bool(self.empreendimentos or self.unidades)

# ── PDF ──────────────────────────────────────────────────────────────────

def ler_pdf(caminho):
    res = ResultadoExtracao(caminho)
    try:
        pdfplumber = instalar('pdfplumber')
        import pdfplumber as pl
    except Exception as e:
        res.erros.append(f"Não foi possível instalar pdfplumber: {e}")
        return res

    nome_arquivo = Path(caminho).stem

    try:
        with pl.open(caminho) as pdf:
            texto_completo = ''
            tabelas_brutas = []

            for pagina in pdf.pages:
                texto_completo += (pagina.extract_text() or '') + '\n'
                tbls = pagina.extract_tables()
                for t in tbls:
                    if t and len(t) > 1:
                        tabelas_brutas.append(t)

        # ── Tenta extrair metadados do empreendimento do texto ────────
        empr = extrair_metadados_texto(texto_completo, nome_arquivo)
        if empr:
            res.empreendimentos.append(empr)

        # ── Processa tabelas encontradas ──────────────────────────────
        for tabela in tabelas_brutas:
            unids = processar_tabela_generica(tabela, nome_arquivo)
            res.unidades.extend(unids)

        if not res.unidades and not res.empreendimentos:
            res.avisos.append(
                "PDF não contém tabelas estruturadas. "
                "Dados de texto extraídos para revisão manual."
            )
            # Salva texto bruto para revisão
            txt_path = OUTPUT_DIR / f"{nome_arquivo}_texto_bruto.txt"
            txt_path.write_text(texto_completo, encoding='utf-8')
            res.avisos.append(f"Texto bruto salvo em: {txt_path}")

    except Exception as e:
        res.erros.append(f"Erro ao ler PDF: {e}")

    return res

# ── EXCEL / XLSX / XLS ───────────────────────────────────────────────────

def ler_excel(caminho):
    res = ResultadoExtracao(caminho)
    try:
        openpyxl = instalar('openpyxl')
        import openpyxl as xl
        xlrd    = instalar('xlrd')
    except:
        pass

    try:
        pd = instalar('pandas')
        import pandas as pnd
    except Exception as e:
        res.erros.append(f"Não foi possível instalar pandas: {e}")
        return res

    nome_arquivo = Path(caminho).stem

    try:
        xls = pnd.ExcelFile(caminho)
        for sheet_name in xls.sheet_names:
            try:
                df = pnd.read_excel(caminho, sheet_name=sheet_name, header=None)
                if df.empty or df.shape[0] < 2:
                    continue

                # Detecta linha de cabeçalho (primeira com mais de 3 células preenchidas)
                header_row = 0
                for i, row in df.iterrows():
                    n_preenchidos = row.notna().sum()
                    if n_preenchidos >= 3:
                        header_row = i
                        break

                df.columns = [str(c).strip().lower() for c in df.iloc[header_row]]
                df = df.iloc[header_row+1:].reset_index(drop=True)
                df = df.dropna(how='all')

                # Tenta detectar se é tabela de unidades ou de empreendimentos
                cols = list(df.columns)
                if _e_tabela_unidades(cols):
                    unids = processar_df_unidades(df, nome_arquivo, sheet_name)
                    res.unidades.extend(unids)
                elif _e_tabela_empreendimentos(cols):
                    emprs = processar_df_empreendimentos(df, nome_arquivo)
                    res.empreendimentos.extend(emprs)
                else:
                    # Tenta unidades mesmo assim
                    unids = processar_df_unidades(df, nome_arquivo, sheet_name)
                    if unids:
                        res.unidades.extend(unids)
                    else:
                        res.avisos.append(
                            f"Aba '{sheet_name}': não reconhecida automaticamente. "
                            f"Colunas: {cols[:8]}"
                        )
            except Exception as e:
                res.avisos.append(f"Aba '{sheet_name}': {e}")

    except Exception as e:
        res.erros.append(f"Erro ao ler Excel: {e}")

    return res

# ── CSV ──────────────────────────────────────────────────────────────────

def ler_csv(caminho):
    res = ResultadoExtracao(caminho)
    nome_arquivo = Path(caminho).stem

    # Detecta encoding e separador
    for enc in ['utf-8', 'latin-1', 'cp1252']:
        for sep in [',', ';', '\t', '|']:
            try:
                with open(caminho, encoding=enc) as f:
                    reader = csv.DictReader(f, delimiter=sep)
                    linhas = list(reader)
                if len(linhas) > 0 and len(linhas[0]) > 1:
                    cols = list(linhas[0].keys())
                    cols_norm = [c.strip().lower() for c in cols]
                    linhas_norm = [
                        {k.strip().lower(): v for k, v in l.items()}
                        for l in linhas
                    ]
                    if _e_tabela_unidades(cols_norm):
                        unids = [_mapear_unidade(l, nome_arquivo) for l in linhas_norm]
                        res.unidades.extend([u for u in unids if u])
                    elif _e_tabela_empreendimentos(cols_norm):
                        emprs = [_mapear_empreendimento(l, nome_arquivo) for l in linhas_norm]
                        res.empreendimentos.extend([e for e in emprs if e])
                    else:
                        # Tenta unidades de forma relaxada
                        unids = [_mapear_unidade(l, nome_arquivo) for l in linhas_norm]
                        validos = [u for u in unids if u and u.get('unidade')]
                        if validos:
                            res.unidades.extend(validos)
                        else:
                            res.avisos.append(
                                f"CSV não reconhecido automaticamente. "
                                f"Colunas: {cols_norm[:8]}"
                            )
                    return res
            except:
                continue

    res.erros.append("Não foi possível ler o CSV (encoding ou separador desconhecido).")
    return res

# ── IMAGEM (OCR) ─────────────────────────────────────────────────────────

def ler_imagem(caminho):
    res = ResultadoExtracao(caminho)
    nome_arquivo = Path(caminho).stem

    try:
        pytesseract = instalar('pytesseract')
        PIL         = instalar('Pillow', 'PIL')
        import pytesseract as tess
        from PIL import Image
    except Exception as e:
        res.erros.append(
            f"OCR não disponível: {e}. "
            "Instale o Tesseract OCR (tesseract-ocr.github.io) e o pacote pytesseract."
        )
        return res

    try:
        img   = Image.open(caminho)
        texto = tess.image_to_string(img, lang='por')
        empr  = extrair_metadados_texto(texto, nome_arquivo)
        if empr:
            res.empreendimentos.append(empr)

        txt_path = OUTPUT_DIR / f"{nome_arquivo}_ocr.txt"
        txt_path.write_text(texto, encoding='utf-8')
        res.avisos.append(
            f"Texto OCR extraído → {txt_path}. "
            "Revise e preencha os campos manualmente se necessário."
        )
    except Exception as e:
        res.erros.append(f"Erro ao processar imagem: {e}")

    return res

# ══════════════════════════════════════════════════════════════════════════
# DETECTORES DE TIPO DE TABELA
# ══════════════════════════════════════════════════════════════════════════

COLS_UNIDADE = {
    'unidade','apto','apartamento','ap','und','unit',
    'bloco','torre','edificio','edifício',
    'andar','pavimento','pav','floor',
    'area','área','metragem','m2','m²',
    'valor','preco','preço','price','vgv',
    'dorm','dormitorio','dormitório','quarto',
    'suite','suíte','garagem','vaga',
    'disponibilidade','status','situacao','situação',
}

COLS_EMPREENDIMENTO = {
    'empreendimento','nome','lançamento','lancamento',
    'construtora','incorporadora','bairro','cidade',
    'entrega','previsao','previsão','launch',
    'comissao','comissão','commission',
}

def _e_tabela_unidades(cols):
    inter = set(c.lower().split()[0] for c in cols) & COLS_UNIDADE
    return len(inter) >= 2

def _e_tabela_empreendimentos(cols):
    inter = set(c.lower().split()[0] for c in cols) & COLS_EMPREENDIMENTO
    return len(inter) >= 2

# ══════════════════════════════════════════════════════════════════════════
# MAPEADORES DE CAMPOS (alias → campo CRM)
# ══════════════════════════════════════════════════════════════════════════

ALIAS_UNIDADE = {
    # unidade
    'unidade':['unidade','apto','apartamento','ap','und','unit','codigo'],
    'bloco':  ['bloco','torre','edificio','edifício','tower','block','ed.'],
    'andar':  ['andar','pavimento','pav','floor','andar/pavimento','piso'],
    # produto
    'area_privativa':['area privativa','área privativa','area priv','ap','m2','área','area','metragem','priv'],
    'area_total':    ['area total','área total','at','total'],
    'quartos':       ['quartos','dorms','dormitorios','dormitórios','dorm','qt.dorm'],
    'suites':        ['suites','suítes','suite','suíte'],
    'banheiros':     ['banheiros','wc','bwc'],
    'vagas':         ['vagas','garagem','vaga','vg','garage'],
    'tipologia':     ['tipologia','tipo','planta','layout','produto'],
    'orientacao':    ['orientacao','orientação','vista','posicao','posição','sol'],
    # financeiro
    'valor_tabela':  ['valor tabela','valor','preço','preco','price','venda','vgv',
                      'valor de venda','valor tabela (r$)','valor (r$)','r$'],
    'valor_desconto':['valor desconto','com desconto','valor desc','desconto r$','preco final'],
    'percentual_desconto':['% desconto','percentual desconto','desconto %','desc%'],
    # status
    'disponibilidade':['disponibilidade','status','situacao','situação','disp','livre'],
    'observacoes':    ['observacoes','observações','obs','notas','remarks'],
}

ALIAS_EMPREENDIMENTO = {
    'nome':            ['nome','empreendimento','lançamento','lancamento','produto','residencial'],
    'construtora_nome':['construtora','incorporadora','empresa','builder'],
    'tipo':            ['tipo','tipologia','produto'],
    'bairro':          ['bairro','neighborhood','distrito'],
    'cidade':          ['cidade','municipio','município','city'],
    'estado':          ['estado','uf','state'],
    'cep':             ['cep','zip','postal'],
    'endereco':        ['endereco','endereço','address','logradouro','rua'],
    'valor_min':       ['valor min','valor mínimo','a partir','ticket min','menor valor','from'],
    'valor_max':       ['valor max','valor máximo','até','ticket max','maior valor'],
    'area_min':        ['area min','área min','menor area','menor área','m2 min'],
    'area_max':        ['area max','área max','maior area','maior área','m2 max'],
    'quartos_min':     ['dorms min','quartos min','dormitorios min','min dorms'],
    'quartos_max':     ['dorms max','quartos max','dormitorios max','max dorms'],
    'vagas_min':       ['vagas min','garagem min'],
    'vagas_max':       ['vagas max','garagem max'],
    'data_lancamento': ['data lançamento','lancamento','data lanc','launch date'],
    'data_entrega':    ['data entrega','previsão entrega','entrega','delivery'],
    'status':          ['status','fase','situacao','situação'],
    'comissao_percentual':['comissao','comissão','commission','% comissão','% comissao'],
    'descricao':       ['descricao','descrição','description','obs','observacoes'],
    'link_material':   ['link','url','material','book','folder'],
}

def _resolver_alias(linha_dict, alias_map):
    """Tenta mapear as chaves de uma linha para os campos canônicos."""
    resultado = {}
    chaves_linha = {k.lower().strip(): v for k, v in linha_dict.items()}
    for campo, aliases in alias_map.items():
        for alias in aliases:
            alias_l = alias.lower().strip()
            # match exato
            if alias_l in chaves_linha:
                resultado[campo] = chaves_linha[alias_l]
                break
            # match parcial
            for chave in chaves_linha:
                if alias_l in chave or chave in alias_l:
                    resultado[campo] = chaves_linha[chave]
                    break
            if campo in resultado:
                break
    return resultado

def _mapear_unidade(linha, fonte=''):
    r = _resolver_alias(linha, ALIAS_UNIDADE)
    # Campos obrigatórios mínimos
    if not r.get('unidade') and not r.get('bloco'):
        return None
    u = r.get('unidade','')
    bloco = r.get('bloco','')
    if not u and bloco:
        u = bloco  # às vezes o campo "bloco" é a unidade inteira

    tip = r.get('tipologia','') or inferir_tipologia(r)
    vt  = limpar_valor(r.get('valor_tabela'))
    vd  = limpar_valor(r.get('valor_desconto'))
    pct = limpar_valor(r.get('percentual_desconto'))
    if vt and vd and not pct:
        pct = round((vt - vd) / vt * 100, 2) if vt else None
    elif vt and pct and not vd:
        vd = round(vt * (1 - pct / 100), 2)

    return {
        'empreendimento_id': r.get('empreendimento_id', ''),   # preenchido depois
        'bloco':             str(bloco).strip() if bloco else '',
        'andar':             limpar_int(r.get('andar')),
        'unidade':           str(u).strip(),
        'tipologia':         str(tip).strip(),
        'area_privativa':    limpar_area(r.get('area_privativa')),
        'area_total':        limpar_area(r.get('area_total')),
        'quartos':           limpar_int(r.get('quartos')),
        'suites':            limpar_int(r.get('suites')),
        'banheiros':         limpar_int(r.get('banheiros')),
        'vagas':             limpar_int(r.get('vagas')),
        'orientacao':        str(r.get('orientacao','')).strip(),
        'valor_tabela':      vt,
        'valor_desconto':    vd,
        'percentual_desconto': pct,
        'disponibilidade':   normalizar_disponibilidade(r.get('disponibilidade','')),
        'observacoes':       str(r.get('observacoes','')).strip(),
        'fonte':             fonte,
    }

def _mapear_empreendimento(linha, fonte=''):
    r = _resolver_alias(linha, ALIAS_EMPREENDIMENTO)
    if not r.get('nome'):
        return None
    return {
        'nome':               str(r['nome']).strip(),
        'construtora_nome':   str(r.get('construtora_nome','')).strip(),
        'tipo':               str(r.get('tipo','Apartamento')).strip(),
        'endereco':           str(r.get('endereco','')).strip(),
        'bairro':             str(r.get('bairro','')).strip(),
        'cidade':             str(r.get('cidade','')).strip(),
        'estado':             str(r.get('estado','SP')).strip(),
        'cep':                str(r.get('cep','')).strip(),
        'valor_min':          limpar_valor(r.get('valor_min')),
        'valor_max':          limpar_valor(r.get('valor_max')),
        'area_min':           limpar_area(r.get('area_min')),
        'area_max':           limpar_area(r.get('area_max')),
        'quartos_min':        limpar_int(r.get('quartos_min')),
        'quartos_max':        limpar_int(r.get('quartos_max')),
        'vagas_min':          limpar_int(r.get('vagas_min')) or 0,
        'vagas_max':          limpar_int(r.get('vagas_max')) or 2,
        'data_lancamento':    limpar_data(r.get('data_lancamento')),
        'data_entrega':       limpar_data(r.get('data_entrega')),
        'status':             str(r.get('status','Em Lançamento')).strip(),
        'descricao':          str(r.get('descricao','')).strip(),
        'link_material':      str(r.get('link_material','')).strip(),
        'comissao_percentual':limpar_valor(r.get('comissao_percentual')) or 0.5,
        'fonte':              fonte,
    }

# ══════════════════════════════════════════════════════════════════════════
# PROCESSADORES DE TABELAS GENÉRICAS (PDF / listas cruas)
# ══════════════════════════════════════════════════════════════════════════

def processar_tabela_generica(tabela, fonte=''):
    """Recebe lista de listas (pdfplumber) e tenta mapear para unidades."""
    if not tabela or len(tabela) < 2:
        return []
    # Primeira linha não-vazia como cabeçalho
    cabecalho = None
    dados = []
    for linha in tabela:
        linha_limpa = [str(c).strip() if c else '' for c in linha]
        if not any(linha_limpa):
            continue
        if cabecalho is None:
            cabecalho = [c.lower() for c in linha_limpa]
        else:
            dados.append(dict(zip(cabecalho, linha_limpa)))

    unids = []
    for d in dados:
        u = _mapear_unidade(d, fonte)
        if u:
            unids.append(u)
    return unids

def processar_df_unidades(df, fonte='', aba=''):
    """Recebe DataFrame pandas e converte para lista de unidades."""
    unids = []
    for _, row in df.iterrows():
        linha = {str(k): str(v) if str(v) not in ('nan','None','') else ''
                 for k, v in row.items()}
        if not any(linha.values()):
            continue
        u = _mapear_unidade(linha, f"{fonte}:{aba}" if aba else fonte)
        if u:
            unids.append(u)
    return unids

def processar_df_empreendimentos(df, fonte=''):
    emprs = []
    for _, row in df.iterrows():
        linha = {str(k): str(v) if str(v) not in ('nan','None','') else ''
                 for k, v in row.items()}
        if not any(linha.values()):
            continue
        e = _mapear_empreendimento(linha, fonte)
        if e:
            emprs.append(e)
    return emprs

def extrair_metadados_texto(texto, nome_arquivo=''):
    """Extrai metadados básicos do empreendimento a partir de texto livre."""
    empr = {'nome': '', 'construtora_nome': '', 'bairro': '', 'cidade': '',
            'estado': 'SP', 'data_entrega': '', 'status': 'Em Lançamento',
            'comissao_percentual': 0.5, 'fonte': nome_arquivo}

    # Nome do empreendimento — linha que contém "Residencial", "Parque", "Torre"...
    padroes_nome = [
        r'(?:Residencial|Parque|Condomínio|Edifício|Torre|Village|Garden|Park|Prime|Vista|Solar|Gran)\s+[\w\s]+',
        r'^([A-Z][A-Za-zÀ-ÿ\s]{3,40})\s*\n',
    ]
    for p in padroes_nome:
        m = re.search(p, texto, re.MULTILINE)
        if m and not empr['nome']:
            empr['nome'] = m.group().strip()[:80]

    if not empr['nome']:
        empr['nome'] = nome_arquivo.replace('_',' ').replace('-',' ').title()

    # Construtora
    m = re.search(
        r'(?:construtora|incorporadora|empreendimento\s+(?:da|de)\s+)[\s:]*([\w\s&.]+)',
        texto, re.I)
    if m:
        empr['construtora_nome'] = m.group(1).strip()[:60]

    # Bairro / cidade
    m = re.search(r'(?:bairro|localização|located)[\s:–-]*([\w\s]+)', texto, re.I)
    if m:
        empr['bairro'] = m.group(1).strip()[:60]

    m = re.search(r'(?:cidade|city|município)[\s:–-]*([\w\s]+)', texto, re.I)
    if m:
        empr['cidade'] = m.group(1).strip()[:60]

    # Data de entrega
    m = re.search(
        r'(?:previsão\s+de\s+)?entrega[\s:–-]*([\w\s/]+(?:20\d{2}|19\d{2}))',
        texto, re.I)
    if m:
        empr['data_entrega'] = limpar_data(m.group(1).strip())

    # Valores
    valores = re.findall(r'R\$\s*([\d.,]+)', texto)
    if valores:
        vals = sorted([limpar_valor(v) for v in valores if limpar_valor(v)])
        if vals:
            empr['valor_min'] = vals[0]
            empr['valor_max'] = vals[-1]

    # Comissão
    m = re.search(r'(?:comiss[aã]o|commission)[\s:]*(\d+[,.]?\d*)\s*%', texto, re.I)
    if m:
        empr['comissao_percentual'] = float(m.group(1).replace(',','.'))

    return empr if empr['nome'] else None

# ══════════════════════════════════════════════════════════════════════════
# GERADOR DE SAÍDA (CSV + SQL)
# ══════════════════════════════════════════════════════════════════════════

def gerar_csv_empreendimentos(emprs):
    if not emprs:
        return None
    caminho = OUTPUT_DIR / f"empreendimentos_import_{TS}.csv"
    campos = ['nome','construtora_nome','tipo','endereco','bairro','cidade','estado',
              'cep','valor_min','valor_max','area_min','area_max','quartos_min',
              'quartos_max','vagas_min','vagas_max','data_lancamento','data_entrega',
              'status','descricao','link_material','comissao_percentual','fonte']
    with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore')
        w.writeheader()
        w.writerows(emprs)
    return caminho

def gerar_sql_empreendimentos(emprs):
    if not emprs:
        return None
    caminho = OUTPUT_DIR / f"empreendimentos_import_{TS}.sql"
    linhas  = [
        "-- ImobiCRM Pro — Importação de Empreendimentos",
        f"-- Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"-- Total: {len(emprs)} empreendimento(s)",
        "",
        "BEGIN TRANSACTION;",
        "",
        "-- Cria construtoras inexistentes automaticamente",
    ]
    construtoras_unicas = list({e['construtora_nome'] for e in emprs if e.get('construtora_nome')})
    for c in construtoras_unicas:
        linhas.append(
            f"INSERT OR IGNORE INTO construtoras (nome) VALUES ({_sql_str(c)});"
        )
    linhas.append("")

    for e in emprs:
        c_sub = (f"(SELECT id FROM construtoras WHERE nome={_sql_str(e.get('construtora_nome',''))} LIMIT 1)"
                 if e.get('construtora_nome') else "NULL")
        linhas.append(
            f"INSERT INTO empreendimentos "
            f"(construtora_id,nome,tipo,endereco,bairro,cidade,estado,cep,"
            f"valor_min,valor_max,area_min,area_max,quartos_min,quartos_max,"
            f"vagas_min,vagas_max,data_lancamento,data_entrega,status,"
            f"descricao,link_material,comissao_percentual) VALUES ("
            f"{c_sub},"
            f"{_sql_str(e.get('nome',''))},"
            f"{_sql_str(e.get('tipo','Apartamento'))},"
            f"{_sql_str(e.get('endereco',''))},"
            f"{_sql_str(e.get('bairro',''))},"
            f"{_sql_str(e.get('cidade',''))},"
            f"{_sql_str(e.get('estado','SP'))},"
            f"{_sql_str(e.get('cep',''))},"
            f"{_sql_num(e.get('valor_min'))},"
            f"{_sql_num(e.get('valor_max'))},"
            f"{_sql_num(e.get('area_min'))},"
            f"{_sql_num(e.get('area_max'))},"
            f"{_sql_num(e.get('quartos_min'))},"
            f"{_sql_num(e.get('quartos_max'))},"
            f"{_sql_num(e.get('vagas_min',0))},"
            f"{_sql_num(e.get('vagas_max',2))},"
            f"{_sql_str(e.get('data_lancamento'))},"
            f"{_sql_str(e.get('data_entrega'))},"
            f"{_sql_str(e.get('status','Em Lançamento'))},"
            f"{_sql_str(e.get('descricao',''))},"
            f"{_sql_str(e.get('link_material',''))},"
            f"{_sql_num(e.get('comissao_percentual',0.5))}"
            f");"
        )
    linhas += ["", "COMMIT;", ""]
    caminho.write_text('\n'.join(linhas), encoding='utf-8')
    return caminho

def gerar_csv_unidades(unidades):
    if not unidades:
        return None
    caminho = OUTPUT_DIR / f"unidades_import_{TS}.csv"
    campos = ['empreendimento_id','bloco','andar','unidade','tipologia',
              'area_privativa','area_total','quartos','suites','banheiros',
              'vagas','orientacao','valor_tabela','valor_desconto',
              'percentual_desconto','disponibilidade','observacoes','fonte']
    with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore')
        w.writeheader()
        w.writerows(unidades)
    return caminho

def gerar_sql_unidades(unidades):
    if not unidades:
        return None
    caminho = OUTPUT_DIR / f"unidades_import_{TS}.sql"
    linhas  = [
        "-- ImobiCRM Pro — Importação de Unidades (Tabelão)",
        f"-- Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"-- Total: {len(unidades)} unidade(s)",
        "-- ATENÇÃO: preencha empreendimento_id antes de executar,",
        "--          ou use a subquery comentada abaixo.",
        "",
        "BEGIN TRANSACTION;",
        "",
    ]
    for u in unidades:
        eid = u.get('empreendimento_id') or 'NULL'
        # Se não tem ID, tenta subquery pelo nome (campo fonte)
        if not eid or eid == '':
            fonte = u.get('fonte','')
            eid = (f"(SELECT id FROM empreendimentos WHERE nome LIKE "
                   f"'%{fonte[:30]}%' LIMIT 1)")
        linhas.append(
            f"INSERT INTO unidades "
            f"(empreendimento_id,bloco,andar,unidade,tipologia,"
            f"area_privativa,area_total,quartos,suites,banheiros,vagas,"
            f"orientacao,valor_tabela,valor_desconto,percentual_desconto,"
            f"disponibilidade,observacoes,fonte) VALUES ("
            f"{eid},"
            f"{_sql_str(u.get('bloco',''))},"
            f"{_sql_num(u.get('andar'))},"
            f"{_sql_str(u.get('unidade',''))},"
            f"{_sql_str(u.get('tipologia',''))},"
            f"{_sql_num(u.get('area_privativa'))},"
            f"{_sql_num(u.get('area_total'))},"
            f"{_sql_num(u.get('quartos'))},"
            f"{_sql_num(u.get('suites'))},"
            f"{_sql_num(u.get('banheiros'))},"
            f"{_sql_num(u.get('vagas'))},"
            f"{_sql_str(u.get('orientacao',''))},"
            f"{_sql_num(u.get('valor_tabela'))},"
            f"{_sql_num(u.get('valor_desconto'))},"
            f"{_sql_num(u.get('percentual_desconto'))},"
            f"{_sql_str(u.get('disponibilidade','Disponível'))},"
            f"{_sql_str(u.get('observacoes',''))},"
            f"{_sql_str(u.get('fonte',''))}"
            f");"
        )
    linhas += ["", "COMMIT;", ""]
    caminho.write_text('\n'.join(linhas), encoding='utf-8')
    return caminho

def _sql_str(v):
    if v is None or str(v).strip() in ('', 'None', 'nan'):
        return 'NULL'
    return "'" + str(v).replace("'", "''") + "'"

def _sql_num(v):
    if v is None or str(v).strip() in ('', 'None', 'nan'):
        return 'NULL'
    try:
        return str(float(v))
    except:
        return 'NULL'

# ══════════════════════════════════════════════════════════════════════════
# RELATÓRIO
# ══════════════════════════════════════════════════════════════════════════

def gerar_relatorio(resultados, arquivos_gerados):
    caminho = OUTPUT_DIR / f"relatorio_extracao_{TS}.txt"
    total_e = sum(len(r.empreendimentos) for r in resultados)
    total_u = sum(len(r.unidades) for r in resultados)

    linhas = [
        "═" * 60,
        "  ImobiCRM Pro — Relatório de Extração",
        f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "═" * 60,
        f"  Arquivos processados : {len(resultados)}",
        f"  Empreendimentos      : {total_e}",
        f"  Unidades             : {total_u}",
        "─" * 60,
    ]
    for r in resultados:
        linhas += [
            f"\n📄 {Path(r.arquivo).name}",
            f"   Empreendimentos: {len(r.empreendimentos)}",
            f"   Unidades:        {len(r.unidades)}",
        ]
        if r.empreendimentos:
            for e in r.empreendimentos:
                linhas.append(f"     • {e.get('nome','')} — {e.get('construtora_nome','')}")
        if r.avisos:
            for a in r.avisos:
                linhas.append(f"   ⚠  {a}")
        if r.erros:
            for e in r.erros:
                linhas.append(f"   ❌ {e}")

    linhas += [
        "\n" + "─" * 60,
        "  Arquivos gerados:",
    ]
    for a in arquivos_gerados:
        if a:
            linhas.append(f"  ✅ {a}")

    linhas += [
        "\n" + "─" * 60,
        "  PRÓXIMOS PASSOS:",
        "  1. Abra os CSVs gerados e revise os dados",
        "  2. Para empreendimentos: ajuste construtora_nome se necessário",
        "  3. Para unidades: preencha a coluna empreendimento_id com o ID correto",
        "     (confira o ID na tela de Empreendimentos do CRM)",
        "  4. Execute o SQL no banco: sqlite3 database/crm.db < arquivo.sql",
        "     OU use o menu Importação no CRM (Configurações → Importar Dados)",
        "═" * 60,
    ]
    caminho.write_text('\n'.join(linhas), encoding='utf-8')
    print('\n'.join(linhas))
    return caminho

# ══════════════════════════════════════════════════════════════════════════
# DISPATCHER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

EXTENSOES = {
    '.pdf':  ler_pdf,
    '.xlsx': ler_excel,
    '.xls':  ler_excel,
    '.xlsm': ler_excel,
    '.csv':  ler_csv,
    '.txt':  ler_csv,
    '.png':  ler_imagem,
    '.jpg':  ler_imagem,
    '.jpeg': ler_imagem,
    '.webp': ler_imagem,
}

def processar_arquivo(caminho):
    ext = Path(caminho).suffix.lower()
    leitor = EXTENSOES.get(ext)
    if not leitor:
        res = ResultadoExtracao(caminho)
        res.erros.append(f"Extensão '{ext}' não suportada. Use: {list(EXTENSOES)}")
        return res
    print(f"  🔍 Processando {Path(caminho).name} ...")
    return leitor(caminho)

def processar_tudo(arquivos):
    resultados = []
    todos_emprs = []
    todas_unids = []

    for arq in arquivos:
        if not Path(arq).exists():
            print(f"  ❌ Arquivo não encontrado: {arq}")
            continue
        r = processar_arquivo(arq)
        resultados.append(r)
        todos_emprs.extend(r.empreendimentos)
        todas_unids.extend(r.unidades)

    # Remove empreendimentos duplicados (mesmo nome)
    vistos = set()
    emprs_unicos = []
    for e in todos_emprs:
        chave = e['nome'].lower().strip()
        if chave not in vistos:
            vistos.add(chave)
            emprs_unicos.append(e)

    print(f"\n  📊 Total: {len(emprs_unicos)} empreendimentos, {len(todas_unids)} unidades")

    arquivos_gerados = [
        gerar_csv_empreendimentos(emprs_unicos),
        gerar_sql_empreendimentos(emprs_unicos),
        gerar_csv_unidades(todas_unids),
        gerar_sql_unidades(todas_unids),
    ]
    rel = gerar_relatorio(resultados, [a for a in arquivos_gerados if a])
    arquivos_gerados.append(rel)
    return arquivos_gerados

# ══════════════════════════════════════════════════════════════════════════
# MODO INTERATIVO (sem argumentos)
# ══════════════════════════════════════════════════════════════════════════

def modo_interativo():
    print("""
╔═══════════════════════════════════════════════════════╗
║     ImobiCRM Pro — Processador de Books e Tabelões    ║
╚═══════════════════════════════════════════════════════╝

Formatos suportados:
  PDF  — books, materiais de venda, tabelões em PDF
  XLSX — tabelões em Excel (qualquer estrutura)
  CSV  — exportações de outros sistemas
  PNG/JPG — imagens de tabelas (requer Tesseract OCR)

Os arquivos de saída serão salvos em: ./importacao_output/
""")
    arquivos = []
    print("Digite o caminho de cada arquivo (Enter em branco para terminar):")
    while True:
        entrada = input(f"  Arquivo {len(arquivos)+1}: ").strip().strip('"').strip("'")
        if not entrada:
            break
        if Path(entrada).exists():
            arquivos.append(entrada)
        else:
            print(f"    ⚠  Arquivo não encontrado: {entrada}")

    if not arquivos:
        print("Nenhum arquivo informado. Encerrando.")
        return

    print(f"\n🚀 Processando {len(arquivos)} arquivo(s)...\n")
    processar_tudo(arquivos)
    print(f"\n✅ Concluído! Arquivos salvos em: {OUTPUT_DIR.resolve()}")

# ══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ImobiCRM — Processador de Books e Tabelões')
    parser.add_argument('--arquivo', '-a', help='Arquivo único para processar')
    parser.add_argument('--pasta',   '-p', help='Pasta com arquivos para processar')
    args = parser.parse_args()

    if args.arquivo:
        processar_tudo([args.arquivo])
    elif args.pasta:
        pasta = Path(args.pasta)
        arquivos = [str(f) for f in pasta.iterdir()
                    if f.suffix.lower() in EXTENSOES]
        if arquivos:
            print(f"📂 {len(arquivos)} arquivo(s) encontrados em {pasta}")
            processar_tudo(arquivos)
        else:
            print(f"Nenhum arquivo suportado encontrado em {pasta}")
    else:
        modo_interativo()
