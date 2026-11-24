PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_completo TEXT NOT NULL CHECK (length(trim(nome_completo)) > 0),
    email TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(email)) > 0),
    senha_hash TEXT NOT NULL,
    perfil_acesso TEXT NOT NULL CHECK (perfil_acesso IN ('OPERADOR', 'GERENTE')),
    status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'INATIVO'))
);

CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido TEXT NOT NULL UNIQUE,
    data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cliente_nome TEXT NOT NULL CHECK (length(trim(cliente_nome)) > 0),
    cliente_documento TEXT NOT NULL CHECK (length(trim(cliente_documento)) > 0),
    forma_pagamento TEXT NOT NULL CHECK (
        forma_pagamento IN ('PIX', 'CARTAO_CREDITO', 'BOLETO_FATURADO')
    ),
    valor_total NUMERIC NOT NULL CHECK (valor_total > 0),
    status_venda TEXT NOT NULL DEFAULT 'CONCLUIDA'
        CHECK (status_venda IN ('CONCLUIDA', 'CANCELADA')),
    chave_autenticidade TEXT NOT NULL UNIQUE,
    usuario_id INTEGER NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS itens_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL,
    produto_id INTEGER NOT NULL,
    quantidade_vendida INTEGER NOT NULL
        CHECK (typeof(quantidade_vendida) = 'integer' AND quantidade_vendida > 0),
    preco_unitario_praticado NUMERIC NOT NULL CHECK (preco_unitario_praticado > 0),
    subtotal_item NUMERIC NOT NULL CHECK (subtotal_item > 0),
    FOREIGN KEY (venda_id) REFERENCES vendas (id) ON DELETE RESTRICT,
    FOREIGN KEY (produto_id) REFERENCES products (id) ON DELETE RESTRICT,
    UNIQUE (venda_id, produto_id)
);

CREATE INDEX IF NOT EXISTS idx_vendas_data_status ON vendas (data_hora, status_venda);
CREATE INDEX IF NOT EXISTS idx_vendas_usuario ON vendas (usuario_id);
CREATE INDEX IF NOT EXISTS idx_itens_venda_venda ON itens_venda (venda_id);
CREATE INDEX IF NOT EXISTS idx_itens_venda_produto ON itens_venda (produto_id);

INSERT OR IGNORE INTO usuarios
    (nome_completo, email, senha_hash, perfil_acesso, status)
VALUES
    ('Operador TechStore', 'operador@techstore.com',
     'pbkdf2:sha256:600000$soV35qlyhT6iMFHc$66fcd5e23bd384f56582ba8e5baa274ca2694ea1db918c0cf999601bb8aae512',
     'OPERADOR', 'ATIVO'),
    ('Gerente TechStore', 'gerente@techstore.com',
     'pbkdf2:sha256:600000$TVQxYCfjt44pgMxE$a711b86876ef6e9c6a744606b4db7d73790ac926de735d113108dde668852ac9',
     'GERENTE', 'ATIVO');

INSERT OR IGNORE INTO vendas
    (numero_pedido, cliente_nome, cliente_documento, forma_pagamento,
     valor_total, status_venda, chave_autenticidade, usuario_id)
SELECT 'TS-DEMO-CANCELADA-001', 'Cliente de demonstração', '00.000.000/0001-00',
       'PIX', 219.90, 'CANCELADA', lower(hex(randomblob(32))), id
FROM usuarios WHERE email = 'gerente@techstore.com';

INSERT OR IGNORE INTO itens_venda
    (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
SELECT v.id, p.id, 1, 219.90, 219.90
FROM vendas AS v
JOIN products AS p ON p.sku = 'HW-RAM-002'
WHERE v.numero_pedido = 'TS-DEMO-CANCELADA-001';

INSERT OR IGNORE INTO vendas
    (numero_pedido, cliente_nome, cliente_documento, forma_pagamento,
     valor_total, status_venda, chave_autenticidade, usuario_id)
SELECT 'TS-DEMO-CANCELADA-002', 'Empresa de demonstração', '11.111.111/0001-11',
       'BOLETO_FATURADO', 899.00, 'CANCELADA', lower(hex(randomblob(32))), id
FROM usuarios WHERE email = 'operador@techstore.com';

INSERT OR IGNORE INTO itens_venda
    (venda_id, produto_id, quantidade_vendida, preco_unitario_praticado, subtotal_item)
SELECT v.id, p.id, 1, 899.00, 899.00
FROM vendas AS v
JOIN products AS p ON p.sku = 'SW-M365-004'
WHERE v.numero_pedido = 'TS-DEMO-CANCELADA-002';
