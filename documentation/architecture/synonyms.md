# Resolução Transparente de Sinônimos

Em ambientes Oracle corporativos, sinônimos privados e públicos (`PUBLIC SYNONYM`) são amplamente utilizados para abstrair o nome real dos schemas, facilitar migrações e acessar objetos remotos via Database Links (`@dblink`).

No entanto, para LLMs e ferramentas tradicionais de documentação, os sinônimos criam uma enorme barreira: o código PL/SQL faz referência a um nome que "não existe" no schema atual, levando a alucinações e perda de rastreabilidade.

---

## 🧩 O Problema

Considere uma procedure no schema `SISTEMA_VENDAS`:

```sql
PROCEDURE PROCESSAR_PEDIDO IS
BEGIN
    INSERT INTO CLIENTES (ID, NOME) VALUES (1, 'Acme Corp');
END;
```

Se o schema `SISTEMA_VENDAS` não possuir uma tabela física chamada `CLIENTES`, a maioria dos copilots assume que a tabela está faltando ou gera código incorreto.

Na realidade, existe um sinônimo:
```sql
CREATE PUBLIC SYNONYM CLIENTES FOR CADASTRO_CENTRAL.TB_CLIENTES_CORP@DBL_MATRIZ;
```

---

## ⚡ Como o LEAI Resolve

O LEAI extrai as views `ALL_SYNONYMS` durante a fase de extração e constrói um resolvedor semântico recursivo:

```mermaid
flowchart LR
    A[Referência no Código:<br/>CLIENTES] -->|Resolve Sinônimo| B[CADASTRO_CENTRAL.TB_CLIENTES_CORP]
    B -->|Identifica DB Link| C[@DBL_MATRIZ]
    C -->|Metadados Unificados| D[Injeção no Contexto da LLM]
```

1. **Desreferenciação Automática:** Ao analisar código PL/SQL ou responder perguntas no `leai ask` / `chat`, referências a sinônimos são mapeadas imediatamente para seus alvos físicos reais.
2. **Suporte a Database Links:** O LEAI identifica quando o objeto alvo reside em uma instância remota através de `@dblink`.
3. **Sem Alucinações:** A IA recebe a definição exata das colunas da tabela física real, mesmo quando o desenvolvedor usa o alias do sinônimo.
