-- ImobiCRM Pro — Importação de Empreendimentos
-- Gerado em: 27/10/2026 13:17
-- Total: 1 empreendimento(s)

BEGIN TRANSACTION;

-- Cria construtoras inexistentes automaticamente
INSERT OR IGNORE INTO construtoras (nome) VALUES ('.
PLANTA TIPO DO APTO. DE 63 M2
SUGESTÃO DE DECORAÇÃO. EVENT');

INSERT INTO empreendimentos (construtora_id,nome,tipo,endereco,bairro,cidade,estado,cep,valor_min,valor_max,area_min,area_max,quartos_min,quartos_max,vagas_min,vagas_max,data_lancamento,data_entrega,status,descricao,link_material,comissao_percentual) VALUES ((SELECT id FROM construtoras WHERE nome='.
PLANTA TIPO DO APTO. DE 63 M2
SUGESTÃO DE DECORAÇÃO. EVENT' LIMIT 1),'Prime House Parque Bussocaba nasceu como
um jardim de oportunidades','Apartamento',NULL,'PLANEJADO
p a r a O s a s c o
E m O s a s c o','projetos que qualificam a paisagem','SP',NULL,NULL,NULL,NULL,NULL,NULL,NULL,0.0,2.0,NULL,NULL,'Em Lançamento',NULL,NULL,0.5);

COMMIT;
