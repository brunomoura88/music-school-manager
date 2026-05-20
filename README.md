# Music School Manager 🎵🚀

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.x-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3.x-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)

O **Music School Manager** é uma plataforma web completa de ERP e gestão escolar desenvolvida sob medida para escolas de música (aplicado em produção no *Estúdio A*). O sistema substitui soluções comerciais genéricas, centralizando o controlo de matrículas, gestão contábil com histórico navegável de competências, gerador dinâmico de contratos comerciais e uma agenda inteligente com validações em tempo real.

---

## 📸 Demonstração Visual

### Painel de Controlo & Agenda Inteligente
> Sistema de matriz dinâmica que destaca as aulas do utilizador autenticado em tempo real e oculta automaticamente agendamentos expirados de recuperação.
<p align="center">
  <img src="img/agenda.png" alt="Agenda Inteligente" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.2);">
</p>

### Gestão Financeira e Fluxo de Caixa
> Módulo de contabilidade com gerador automático de mensalidades e seletor dinâmico de competências históricas.
<p align="center">
  <img src="img/financeiro.png" alt="Módulo Financeiro" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.2);">
</p>

### Autenticação Segura (Portal do Professor)
> Sistema com criptografia avançada de palavras-passe e controlo rígido de sessões de utilizadores.
<p align="center">
  <img src="img/login.png" alt="Ecrã de Login" width="90%" style="border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.2);">
</p>

---

## 🔥 Funcionalidades em Destaque (Engenharia de Software)

* **Arquitetura Baseada em Matriz de Horários:** Implementação de um dicionário indexado bidimensional `(dia, hora)` no Python que mapeia dinamicamente a grade de aulas, otimizando o consumo de memória e evitando colisões de horários.
* **Lógica Temporal Automática:** Algoritmo executado no servidor que analisa o relógio global e oculta automaticamente da grade as aulas do tipo *Recuperação* assim que o horário agendado expira no dia corrente.
* **Segurança e Criptografia (Migrador Automático):** Armazenamento seguro de credenciais utilizando a biblioteca `Werkzeug` (Scrypt/PBKDF2). O sistema conta com um gatilho de migração transparente que encripta de forma automática as palavras-passe antigas no momento do primeiro login do utilizador.
* **Impressão Dinâmica de Contratos:** Módulo gerador de contratos de prestação de serviços em HTML/CSS formatados com quebras de página nativas para impressão física ou exportação limpa para PDF.
* **Navegação Histórica de Caixa:** Filtros dinâmicos que isolam receitas e despesas por mês/ano (competência), permitindo auditoria financeira completa da instituição.

---

## 🛠️ Tecnologias de Desenvolvimento

* **Backend:** Python 3.10+ com Microframework Flask
* **Persistência de Dados:** SQLite3 com mapeamento relacional relacional puro (Queries SQL otimizadas com cláusulas `JOIN` e `UPDATE` cirúrgicos)
* **Frontend e UX:** HTML5, CSS3, Bootstrap 5 (Tema Escuro Customizado com Paleta de Cores corporativa em tons de Bordô, Grafite e Ouro)
* **Motor de Templates:** Jinja2 (Utilização de filtros avançados de renderização segura como `|safe`)
* **Segurança:** Controlo de Sessões do Flask (`session`) e Encriptação com `Werkzeug.security`

---

## 🚀 Como Executar o Projeto Localmente

### 1. Clonar o Repositório
```bash
git clone [https://github.com/TEU_USUARIO/music-school-manager.git](https://github.com/TEU_USUARIO/music-school-manager.git)
cd music-school-manager