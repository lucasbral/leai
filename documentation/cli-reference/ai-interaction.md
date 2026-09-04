# Interação com IA (ask, chat, models)

O LEAI transforma seu catálogo Oracle em uma base de conhecimento interativa capaz de responder dúvidas complexas de engenharia e regras de negócio no terminal.

---

## 1. `leai ask <PERGUNTA>`

Permite fazer perguntas pontuais em linguagem natural sobre qualquer aspecto do banco de dados.

```bash
leai ask "Como funciona a regra de rescisão na procedure CALC_RESCISAO e quais tabelas ela consulta?"
```

### O que acontece internamente:
1. O LEAI analisa as entidades mencionadas na pergunta.
2. Recupera dinamicamente a linhagem e as definições das tabelas e procedimentos envolvidos.
3. Se houver pacotes grandes, comprime o código PL/SQL semanticamente para poupar tokens.
4. Envia o contexto cirúrgico para a LLM configurada e exibe a resposta formatada em Markdown no terminal.

---

## 2. `leai chat`

Inicia um console interativo no terminal onde você pode conversar livremente com o agente de banco de dados.

```bash
leai chat
```

### Funcionalidades do Chat:
* **Execução Autônoma de Ferramentas:** Durante a conversa, o modelo pode chamar ferramentas offline (`search_database_objects`, `view_object_definition`, `trace_object_lineage`) para inspecionar schemas e sanar dúvidas antes de responder.
* **Histórico Conversacional:** Mantém o contexto de perguntas anteriores na mesma sessão.
* **Comandos Especiais:**
  * `/help`: Exibe comandos disponíveis na sessão interativa.
  * `/clear`: Limpa o histórico da conversa atual.
  * `/exit` ou `quit`: Encerra o chat.

---

## 3. `leai models`

Exibe a lista de provedores de IA suportados, modelos recomendados e permite testar a conectividade de suas chaves de API com medição de latência.

```bash
leai models
```

### Saída de Diagnóstico:
O comando exibe uma tabela indicando:
* Provedor (OpenAI, Gemini, Claude, DeepSeek, Ollama, Bedrock, etc.).
* Status da chave de API (`CONFIGURADO` ou `NÃO DETECTADO`).
* Teste de latência de ping em milissegundos.
