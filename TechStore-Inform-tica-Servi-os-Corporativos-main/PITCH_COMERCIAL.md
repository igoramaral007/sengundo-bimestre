# Pitch comercial B2B — TechStock Manager

**Empresa apresentada:** TechStore Informática & Serviços Corporativos  
**Duração:** 10 minutos de pitch + até 5 minutos de sabatina  
**Site da demonstração:** `http://127.0.0.1:5000/showroom`

> Preencha os nomes dos integrantes junto aos papéis antes da apresentação. Os valores abaixo são uma proposta didática para o pitch, não uma cotação aprovada.

## Preparação

- Deixe o servidor iniciado e abra a vitrine pública no navegador.
- A vitrine tem ilustrações originais para os seis itens de demonstração. Se a equipe tiver fotos reais, o gerente pode enviá-las pela própria vitrine.
- Tenha as contas de avaliação do README disponíveis e faça a demonstração de permissões em sessões separadas.
- Não use dados reais de clientes durante a demo.
- Não apresente o protótipo local como um SaaS já hospedado: hospedagem, backups monitorados e SLA são parte da proposta de implantação, não funcionalidades de infraestrutura já entregues.

## Ato 1 — Abertura comercial e proposta de valor (2 min)

**Responsável:** Comercial / Gerente de Projetos  
**Tela:** `http://127.0.0.1:5000/showroom`

**Fala sugerida**

> Bom dia. Somos a TechStore Informática & Serviços Corporativos e apresentamos o TechStock Manager integrado ao módulo de PDV. Nossa proposta é dar à TechStore controle confiável desde a consulta do produto até o registro da venda e da movimentação de estoque.
>
> No diagnóstico, identificamos quatro riscos: ruptura de itens importantes, venda sem conferência de saldo, divergência no fechamento do caixa e dificuldade para rastrear quem realizou cada operação. Quando catálogo, estoque e venda ficam desconectados, a equipe perde tempo e a gestão toma decisões com informação incompleta.
>
> A solução consolida hardware, periféricos e licenças digitais em uma vitrine pesquisável; valida o saldo no fechamento; registra cada venda e seus itens; e gera movimentações auditáveis. O objetivo comercial é reduzir erros operacionais e dar à gerência uma trilha verificável para cada saída.
>
> Nesta vitrine, o cliente consegue comparar especificações, preço e disponibilidade antes de iniciar uma compra. A equipe pode substituir as ilustrações de demonstração por fotos reais dos produtos.

**Transição:** “Agora vamos percorrer uma venda real no sistema.”

## Ato 2 — Demonstração ao vivo (4 min)

**Responsável:** Produto / QA  
**Sem slides nesta etapa.**

1. **Catálogo e alertas (45 s):** abra a vitrine; pesquise por “SSD”; use o filtro de licenças digitais; mostre descrição, modalidade de licença, preço e disponibilidade. Acesse também o painel para destacar o alerta de reposição do estoque baixo.
2. **RBAC (45 s):** mostre a sessão de operador, que consulta catálogo e opera o checkout. Tente abrir `/products/new` com esse perfil e mostre a resposta `403`. Encerre a sessão e entre como gerente para mostrar que o cadastro e os ajustes ficam restritos à gerência.
3. **Venda multi-itens (90 s):** volte à vitrine e inicie a venda. No checkout, use um cliente fictício, selecione PIX, adicione uma Memória DDR4 16 GB e uma licença Microsoft 365 Business Standard. Confira foto/ilustração, especificações, quantidades e total antes de confirmar.
4. **Recibo e livro-razão (30 s):** conclua a venda; abra o recibo e mostre número do pedido, cliente, itens, valores, operador e chave de autenticidade. Na sessão gerencial, abra as movimentações e localize as saídas vinculadas ao pedido.
5. **Rollback por falta de estoque (30 s):** inicie outra venda com um item válido e tente adicionar 5 unidades de Windows 11 Pro, cujo saldo demonstrativo é menor. Mostre a mensagem de saldo insuficiente e confira que nenhuma parte da venda nem movimentação parcial foi gravada.

**Resultado a verbalizar:** “O navegador informa o saldo, mas a decisão final é revalidada pelo servidor dentro da transação. Por isso, não dependemos do valor exibido na tela.”

## Ato 3 — Arquitetura técnica e segurança (2 min)

**Responsável:** Líder Técnico / Desenvolvimento  
**Tela:** diagrama ou `database.sql` e `app.py`, sem interromper a demo principal.

> O modelo mantém sete tabelas: `categories`, `suppliers`, `products`, `movements`, `usuarios`, `vendas` e `itens_venda`. As chaves estrangeiras ligam produtos a categoria e fornecedor, movimentações a produtos, vendas a usuários e itens aos respectivos produtos e vendas. Restrições `CHECK` validam tipos, quantidades e valores; `UNIQUE` protege SKU, e-mail, número do pedido e chave de autenticidade.
>
> No checkout, o backend inicia `BEGIN IMMEDIATE`, consulta preço e saldo atuais no banco, cria a venda, grava os itens, debita cada produto com a condição `stock >= quantidade` e registra as saídas. Só confirma com `COMMIT` quando todas as etapas passam; qualquer insuficiência ou falha de integridade executa `ROLLBACK`.
>
> As rotas verificam o perfil no servidor, consultas usam parâmetros, e senhas são armazenadas com hash PBKDF2-SHA256. SQLite é adequado para esta demonstração local; antes de uma implantação multiusuário em produção, dimensionaríamos banco, hospedagem, cópias de segurança e monitoramento conforme a carga contratada.

**Transição:** “Com o funcionamento e os controles demonstrados, segue a proposta de implantação.”

## Ato 4 — Proposta comercial e fechamento (2 min)

**Responsável:** Comercial / PM

| Item proposto | Valor demonstrativo | Inclui |
|---|---:|---|
| Implantação (pagamento único) | R$ 4.900,00 | Configuração inicial, importação assistida do catálogo, treinamento e acompanhamento da entrada em operação |
| Licença, hospedagem e suporte (mensal) | R$ 690,00/mês | Hospedagem contratada, atualizações corretivas, backup monitorado e suporte em horário comercial |
| SLA de atendimento | Incluso no plano mensal | Confirmação de abertura em até 4 horas úteis; prazo de solução definido por prioridade e escopo |

**Fala sugerida**

> Propomos iniciar com a implantação, validar o catálogo e os perfis de acesso com a equipe e acompanhar a entrada em operação. A mensalidade cobre o ambiente e o suporte descritos na proposta. Os valores são uma referência para esta apresentação e seriam fechados após validar volume de dados, usuários, infraestrutura e SLA.
>
> A demo comprovou o fluxo de catálogo, venda, recibo, movimentação e bloqueio por saldo insuficiente. Podemos avançar para o levantamento de implantação e formalizar escopo, cronograma, segurança e níveis de serviço. Podemos agendar essa etapa?

## Sabatina técnica — preparação de 5 min

### Perguntas prováveis e respostas curtas

**Por que existem sete tabelas?**  
Elas separam cadastros, estoque, identidade e vendas: quatro tabelas operacionais (`categories`, `suppliers`, `products`, `movements`) e três do fluxo comercial (`usuarios`, `vendas`, `itens_venda`). Imagens são colunas opcionais de `products`, portanto não criam uma oitava tabela.

**Como o rollback é comprovado?**  
O teste `test_insufficient_later_item_rolls_back_entire_checkout` envia primeiro um item disponível e depois uma quantidade impossível. Verifica que saldo, número de vendas e livro de movimentações permanecem sem alterações parciais.

**O que impede alterar o preço pelo navegador?**  
O checkout envia IDs e quantidades. O backend busca o preço vigente no banco e grava uma cópia histórica em `itens_venda`; o valor enviado pelo cliente não é usado para faturar.

**Como a venda aparece no livro-razão?**  
Cada item vendido gera uma movimentação de saída identificada com o número do pedido. O cancelamento gerencial mantém a venda como histórico, registra o estorno e devolve o saldo em uma transação.

**Por que SQLite? Ele suporta muitos caixas simultâneos?**  
É simples para demonstração e uso local. SQLite serializa escritores; para crescimento e múltiplas estações concorrentes, a proposta de produção deve avaliar um banco servidor como PostgreSQL e testar a carga real.

**O sistema integra pagamento ou emite NF-e?**  
Não. A demo registra a forma de pagamento e gera um recibo interno com chave de autenticidade. Gateway de pagamento, emissão fiscal e integração contábil não fazem parte do protótipo atual e exigiriam escopo e homologação próprios.

**O que acontece se o processo falhar durante a venda?**  
Antes do `COMMIT`, o SQLite desfaz as alterações pendentes; depois do `COMMIT`, a transação está persistida. Continuidade operacional também exige rotina de backup e restauração testada, item previsto para o ambiente contratado e não apresentado como automação já instalada no protótipo.

**Onde ficam as permissões?**  
Nos decoradores `login_required` e `roles_required` do `app.py`. A interface também oculta controles, mas a proteção real é a verificação de perfil na rota.

### Arquivos para localizar durante a sabatina

- `app.py`: autenticação, RBAC, cadastro, upload de imagens, checkout e cancelamento.
- `database.sql`: quatro tabelas iniciais e restrições do catálogo/estoque.
- `migration_v2.sql`: usuários, vendas e itens de venda.
- `tests/test_app.py`: testes de permissões, venda multi-itens, rollback, recibo e upload.

