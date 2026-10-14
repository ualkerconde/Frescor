# Arquivos de exemplo para testar a importação

Arquivos CSV no formato aceito pela tela **Importar** (colunas
`data;codigo_loja;codigo_produto;quantidade`, separador `;`, vírgula decimal,
data `dd/mm/aaaa`). Usam as lojas `001` e `002` e os produtos do seed de
desenvolvimento (`backend/scripts/seed_dev.py` e `seed_produtos.py`).

| Arquivo | O que acontece ao importar como **Vendas** |
|---|---|
| `vendas_valido.csv` | **Grava 4 vendas** (10 e 11/08/2026, lojas 001 e 002). Na primeira vez: "4 linhas importadas · Todas são novas". Importando de novo: "0 novas · 4 substituídas". |
| `vendas_com_erros.csv` | **Não grava nada.** "Nada foi gravado: 2 erros" — linha 3 (data 31/02/2026 não existe) e linha 4 (produto `NAO-EXISTE`). |

Atenção: o `vendas_valido.csv` grava de verdade no banco que estiver
configurado. Use só no ambiente de desenvolvimento.
