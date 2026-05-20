from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import datetime
# Importa o gerador e o checador de hashes de senha seguros
from werkzeug.security import generate_password_hash, check_password_hash
import os

# --- TRUQUE DE ARQUITETURA: CONEXÃO DINÂMICA INTEGRADA ---

def is_sqlite_conn(conn):
    return conn.__class__.__module__.startswith('sqlite3')

def obter_conexao():
    # O Render define automaticamente esta variável na nuvem
    url_banco = os.environ.get("DATABASE_URL")
    
    if url_banco:
        import psycopg
        from psycopg.rows import dict_row
        
        # Remove qualquer quebra de linha ou espaço que venha da variável do Render
        url_banco = url_banco.strip()
        
        if url_banco.startswith("postgres://"):
            url_banco = url_banco.replace("postgres://", "postgresql://", 1)
            
        # Conecta de forma limpa e direta
        return psycopg.connect(url_banco, row_factory=dict_row)
    else:
        # Se estiver no seu computador, usa o seu SQLite local de sempre
        sqlite_conn = sqlite3.connect('estudio_a.db')
        sqlite_conn.row_factory = sqlite3.Row

        class SQLiteCursorWrapper:
            def __init__(self, cursor):
                self._cursor = cursor

            def execute(self, query, params=None):
                if params is None:
                    params = ()
                return self._cursor.execute(query.replace('%s', '?'), params)

            def executemany(self, query, param_seq):
                return self._cursor.executemany(query.replace('%s', '?'), param_seq)

            def __getattr__(self, name):
                return getattr(self._cursor, name)

        class SQLiteConnectionWrapper:
            def __init__(self, conn):
                self._conn = conn

            def cursor(self, *args, **kwargs):
                c = self._conn.cursor(*args, **kwargs)
                return SQLiteCursorWrapper(c)

            def commit(self):
                return self._conn.commit()

            def close(self):
                return self._conn.close()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                self._conn.close()

            def __getattr__(self, name):
                return getattr(self._conn, name)

        return SQLiteConnectionWrapper(sqlite_conn)

app = Flask(__name__)

# === RECRIADA A FUNÇÃO CORRETA PARA INICIALIZAR O BANCO ===
def init_db():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    # Verifica se estamos usando PostgreSQL (psycopg) ou SQLite
    is_postgres = hasattr(conn, 'encoding') or conn.__class__.__name__ == 'Connection'
    
    # Define os tipos de autoincremento para cada banco
    id_auto = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    text_type = "VARCHAR(255)" if is_postgres else "TEXT"
    text_long = "TEXT"
    real_type = "NUMERIC(10,2)" if is_postgres else "REAL"
    
    # 1. Tabela de Professores
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS professores (
            id {id_auto},
            nome {text_type} NOT NULL,
            cpf {text_type} UNIQUE NOT NULL,
            login {text_type},
            senha {text_type}
        );
    ''')

    # 2. Tabela de Disciplinas
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS disciplinas (
            id {id_auto},
            nome {text_type} UNIQUE NOT NULL
        );
    ''')

    # 3. Tabela de Salas
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS salas (
            id {id_auto},
            nome {text_type} UNIQUE NOT NULL
        );
    ''')
    
    # 4. Tabela de Alunos
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS alunos (
            id {id_auto},
            nome {text_type} NOT NULL,
            cpf {text_type},
            telefone {text_type},
            instrumento {text_type},
            dia_aula {text_type},
            horario_aula {text_type},
            id_disciplina INTEGER REFERENCES disciplinas(id),
            id_professor INTEGER REFERENCES professores(id),
            valor_mensalidade {real_type},
            vencimento_mensalidade {text_type},
            dia_vencimento INTEGER,
            dia_semana {text_type},
            cpf_rg {text_type},
            endereco {text_long},
            pago INTEGER DEFAULT 0
        );
    ''')
    
    # 5. Tabela de Agenda
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS agenda (
            id {id_auto},
            id_sala INTEGER,
            id_professor INTEGER,
            id_aluno INTEGER,
            dia_semana {text_type} NOT NULL,
            horario {text_type} NOT NULL,
            tipo_aula {text_type} DEFAULT 'Regular',
            data_aula {text_type}
        );
    ''')
    
    # 6. Tabela de Financeiro
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS financeiro (
            id {id_auto},
            aluno_id INTEGER,
            mes_referencia {text_type} NOT NULL,
            valor {real_type} NOT NULL,
            status {text_type} DEFAULT 'Pendente',
            data_pagamento {text_type},
            tipo {text_type} DEFAULT 'Receita',
            descricao {text_long}
        );
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

# Executa a inicialização obrigatória do banco apenas no modo local
# ao rodar diretamente com python app.py.
# O Gunicorn não importa init_db() no import, evitando falhas de startup.

def popular_dados_iniciais():
    conn = obter_conexao()
    cursor = conn.cursor()

    # Garante que as disciplinas básicas existam
    disciplinas = [('Violão',), ('Guitarra',), ('Teclado',), ('Bateria',), ('Canto',), ('Contra-Baixo',)]
    cursor.executemany("INSERT INTO disciplinas (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING;", disciplinas)

    # Garante que as salas básicas existam
    salas = [('Sala 01',), ('Sala 02',)]
    cursor.executemany("INSERT INTO salas (nome) VALUES (%s) ON CONFLICT (nome) DO NOTHING;", salas)

    # CADASTRO REAL DE TODOS OS PROFESSORES DA ESCOLA
    professores = [
        ('Bruno Moura', '123', 'bruno', generate_password_hash('estudioa123')),
        ('Bruno Mota', '456', 'brunomota', generate_password_hash('estudioa123')),
        ('Raphael Russowsky', '789', 'raphael', generate_password_hash('estudioa123')),
        ('Guilherme Martins', '101', 'guilherme', generate_password_hash('estudioa123')),
        ('Beatriz Ribeiro', '202', 'beatriz', generate_password_hash('estudioa123'))
    ]
    
    for nome, cpf, login, senha in professores:
        cursor.execute("SELECT id FROM professores WHERE nome = %s;", (nome,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO professores (nome, cpf, login, senha) 
                VALUES (%s, %s, %s, %s);
            ''', (nome, cpf, login, senha))

    conn.commit()
    cursor.close()
    conn.close()

def aplicar_migracoes():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    # Verifica se estamos usando SQLite para a função is_sqlite_conn nativa
    is_postgres = hasattr(conn, 'encoding') or conn.__class__.__name__ == 'Connection'
    id_auto = 'SERIAL PRIMARY KEY' if is_postgres else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    real_type = "NUMERIC(10,2)" if is_postgres else "REAL"
    
    # Tenta rodar as migrações prevenindo falhas no Postgres
    tabelas_colunas = [
        ("professores", "login TEXT"),
        ("professores", "senha TEXT"),
        ("alunos", "cpf_rg TEXT"),
        ("alunos", "endereco TEXT"),
        ("alunos", "dia_vencimento INTEGER"),
        ("alunos", "pago INTEGER DEFAULT 0"),
        ("alunos", "dia_semana TEXT"),
        ("alunos", "id_disciplina INTEGER"),
        ("alunos", "id_professor INTEGER"),
        ("alunos", "vencimento_mensalidade TEXT"),
        ("agenda", "id_sala INTEGER"),
        ("agenda", "id_professor INTEGER"),
        ("agenda", "id_aluno INTEGER"),
        ("agenda", "tipo_aula TEXT DEFAULT 'Fixa'"),
        ("agenda", "data_aula TEXT")
    ]
    
    for tabela, coluna in tabelas_colunas:
        try:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna};")
            conn.commit()
        except Exception:
            pass

    try:
        cursor.execute("UPDATE agenda SET id_professor = professor_id WHERE id_professor IS NULL AND professor_id IS NOT NULL;")
        cursor.execute("UPDATE agenda SET id_aluno = aluno_id WHERE id_aluno IS NULL AND aluno_id IS NOT NULL;")
        cursor.execute("UPDATE agenda SET data_aula = data_recuperacao WHERE data_aula IS NULL AND data_recuperacao IS NOT NULL;")
        conn.commit()
    except Exception:
        pass

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS mensalidades (
            id {id_auto},
            id_aluno INTEGER NOT NULL,
            competencia VARCHAR(50) NOT NULL,
            valor_devido {real_type} NOT NULL,
            status VARCHAR(50) NOT NULL,
            data_pagamento VARCHAR(50),
            FOREIGN KEY (id_aluno) REFERENCES alunos(id)
        );
    ''')
    conn.commit()
    cursor.close()
    conn.close()

# ==========================================
# ROTAS DO SISTEMA
# ==========================================
@app.route('/', methods=['GET', 'POST'])
def login():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    # TRUQUE DE INFRAESTRUTURA: Cria as colunas de login e senha nos professores caso não existam
    try:
        cursor.execute("ALTER TABLE professores ADD COLUMN login TEXT;")
        cursor.execute("ALTER TABLE professores ADD COLUMN senha TEXT;")
        conn.commit()
    except Exception:
        pass # Se já existirem, ignora e segue

    erro = None

    if request.method == 'POST':
        usuario_input = request.form.get('cpf') # mantemos o name do input antigo para não quebrar o HTML
        senha_input = request.form.get('senha')

        cursor.execute("SELECT id, nome, senha FROM professores WHERE login = %s OR cpf = %s;", (usuario_input, usuario_input))
        professor = cursor.fetchone()

        if professor:
            id_prof, nome_prof, senha_banco = professor
            
            # Ajuste de Segurança: se a senha no banco for texto limpo igual à digitada, ou se bater com o hash
            if senha_banco == senha_input or (senha_banco and senha_banco.startswith(('scrypt:', 'pbkdf2:')) and check_password_hash(senha_banco, senha_input)):
                
                # Se a senha antiga era texto limpo, vamos atualizá-la automaticamente para hash agora mesmo!
                if senha_banco == senha_input:
                    senha_com_hash = generate_password_hash(senha_input)
                    cursor.execute("UPDATE professores SET senha = %s WHERE id = %s;", (senha_com_hash, id_prof))
                    conn.commit()

                # CRIANDO O CARIMBO DA SESSÃO
                session['professor_id'] = id_prof
                session['professor_nome'] = nome_prof
                conn.close()
                return redirect('/dashboard')
            else:
                erro = "Senha incorreta!"
        else:
            erro = "Professor não encontrado!"

    conn.close()
    return render_template('login.html', erro=erro)
# ROTA DE LOGOUT: Para o professor sair com segurança e apagar o carimbo
@app.route('/logout')
def logout():
    # Limpa o carimbo da sessão, deslogando o usuário
    session.clear()
    # Redireciona instantaneamente de volta para a tela de login (raiz '/')
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'professor_id' not in session:
        return redirect('/')

    id_logado = session['professor_id']
    nome_logado = session['professor_nome']

    conn = obter_conexao()
    cursor = conn.cursor()

    # --- 1. CONTAR ALUNOS ATIVOS ---
    if nome_logado == 'Bruno Moura':
        # Você vê o total de todos os alunos da escola
        cursor.execute("SELECT COUNT(*) FROM alunos;")
    else:
        # Professores comuns só vêem a contagem dos seus próprios alunos
        cursor.execute("SELECT COUNT(*) FROM alunos WHERE id_professor = %s;", (id_logado,))
    total_alunos = cursor.fetchone()[0]

    # --- 2. CONTAR AULAS DE HOJE ---
    # Mapeamento dos dias para bater com o formato de texto que você usa na agenda
    dias_semana_pt = {
        0: 'Segunda', 1: 'Terça', 2: 'Quarta',
        3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'
    }
    dia_atual_num = datetime.now().weekday()
    dia_atual_pt = dias_semana_pt[dia_atual_num]

    if nome_logado == 'Bruno Moura':
        # Buscamos na tabela AGENDA quantas aulas estão marcadas para hoje na escola inteira
        cursor.execute("SELECT COUNT(*) FROM agenda WHERE dia_semana = %s;", (dia_atual_pt,))
    else:
        # Professores comuns vêem quantas aulas eles têm na AGENDA hoje
        cursor.execute("SELECT COUNT(*) FROM agenda WHERE dia_semana = %s AND id_professor = %s;", (dia_atual_pt, id_logado))
    aulas_hoje = cursor.fetchone()[0]

    conn.close()

    # --- 3. DEFINIR MÊS/ANO ATUAL ---
    meses_ano = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    mes_atual = meses_ano[datetime.now().month - 1]
    ano_atual = datetime.now().year
    competencia_atual = f"{mes_atual}/{ano_atual}"

    # Retorna o template passando os dados reais descobertos
    return render_template(
        'dashboard.html', 
        nome_professor=nome_logado,
        total_alunos=total_alunos,
        aulas_hoje=aulas_hoje,
        competencia=competencia_atual
    )

# ==========================================
# ROTAS DE ALUNOS (COM EXCLUSÃO)
# ==========================================
@app.route('/alunos', methods=['GET', 'POST'])
def alunos():
    if 'professor_id' not in session:
        return redirect('/')

    id_logado = session['professor_id']
    nome_logado = session['professor_nome']

    conn = obter_conexao()
    cursor = conn.cursor()

    # 1. PROCESSAR CADASTRO DE NOVO ALUNO (POST)
    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone')
        instrumento = request.form.get('instrumento')
        dia_aula = request.form.get('dia_aula')
        horario_aula = request.form.get('horario_aula')
        id_disciplina = request.form.get('id_disciplina')
        valor_mensalidade = request.form.get('valor')
        dia_semana = request.form.get('dia_semana') # Mantém o dia que já tinhas
        
        # NOVOS CAMPOS CAPTURADOS DO TEU FORMULÁRIO:
        cpf_rg = request.form.get('cpf_rg') if request.form.get('cpf_rg') else request.form.get('cpf')
        endereco = request.form.get('endereco')
        dia_vencimento = request.form.get('dia_vencimento')
        
        # VÍNCULO AUTOMÁTICO DO PROFESSOR LOGADO
        id_professor_vinc = id_logado 

        cursor.execute('''
            INSERT INTO alunos (nome, id_disciplina, valor_mensalidade, dia_semana, id_professor, cpf_rg, endereco, dia_vencimento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        ''', (nome, id_disciplina, valor_mensalidade, dia_semana, id_professor_vinc, cpf_rg, endereco, dia_vencimento))
        
        conn.commit()
        conn.close() # Lembra-te de fechar a conexão antes do redirect
        return redirect('/alunos')

    # 2. LISTAGEM DINÂMICA DE ALUNOS (GET)
    # REGRA DE ADMINISTRAÇÃO: Bruno Moura (Supondo que seu ID seja 1) vê tudo.
    # Se você quiser usar o seu nome em vez do ID para garantir, fazemos a checagem por nome:
    # 2. LISTAGEM DINÂMICA DE ALUNOS (GET)
    if nome_logado == 'Bruno Moura':
        cursor.execute('''
            SELECT al.id, al.nome, al.vencimento_mensalidade, al.valor_mensalidade, p.nome, d.nome
            FROM alunos al
            LEFT JOIN disciplinas d ON al.id_disciplina = d.id
            LEFT JOIN professores p ON al.id_professor = p.id;
        ''')
    else:
        cursor.execute('''
            SELECT al.id, al.nome, al.vencimento_mensalidade, al.valor_mensalidade, p.nome, d.nome
            FROM alunos al
            LEFT JOIN disciplinas d ON al.id_disciplina = d.id
            LEFT JOIN professores p ON al.id_professor = p.id
            WHERE al.id_professor = %s;
        ''', (id_logado,))
        
    alunos_lista = cursor.fetchall()

    # Buscar disciplinas para preencher o campo Select do formulário
    cursor.execute("SELECT id, nome FROM disciplinas;")
    disciplinas_lista = cursor.fetchall()

    # Buscar professores para preencher o select do formulário
    cursor.execute("SELECT id, nome FROM professores;")
    professores_lista = cursor.fetchall()

    conn.close()

    return render_template('alunos.html', alunos=alunos_lista, disciplinas=disciplinas_lista, professores=professores_lista)
# NOVA ROTA: Rota para deletar o aluno do sistema
@app.route('/excluir_aluno/<int:id>')
def excluir_aluno(id):
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alunos WHERE id = %s;", (id,))
    conn.commit()
    conn.close()
    return redirect('/alunos')

@app.route('/aluno/editar/<int:id_aluno>', methods=['GET', 'POST'])
def editar_aluno(id_aluno):
    if 'professor_id' not in session:
        return redirect('/')

    id_logado = session['professor_id']
    conn = obter_conexao()
    cursor = conn.cursor()

    # --- FORMATO GET: CARREGA OS DADOS ATUAIS NO FORMULÁRIO ---
    if request.method == 'GET':
        # Busca os dados cadastrais do aluno específico
        cursor.execute('''
            SELECT id, nome, cpf_rg, endereco, vencimento_mensalidade, valor_mensalidade, id_disciplina, id_professor 
            FROM alunos 
            WHERE id = %s;
        ''', (id_aluno,))
        aluno_dados = cursor.fetchone()

        if not aluno_dados:
            conn.close()
            return "Aluno não encontrado!", 404

        # Busca as listas de disciplinas e professores para preencher os campos de seleção (Selects)
        cursor.execute("SELECT id, nome FROM disciplinas;")
        disciplinas_lista = cursor.fetchall()

        cursor.execute("SELECT id, nome FROM professores;")
        professores_lista = cursor.fetchall()

        conn.close()
        return render_template('editar_aluno.html', aluno=aluno_dados, disciplinas=disciplinas_lista, professores=professores_lista)

    # --- FORMATO POST: SALVA AS ALTERAÇÕES NO BANCO ---
    elif request.method == 'POST':
        nome = request.form.get('nome')
        cpf_rg = request.form.get('cpf')
        endereco = request.form.get('endereco')
        vencimento_mensalidade = request.form.get('dia_vencimento')
        valor_mensalidade = request.form.get('valor')
        id_disciplina = request.form.get('id_disciplina')
        id_professor = request.form.get('id_professor')

        # Faz a atualização cirúrgica usando o UPDATE
        cursor.execute('''
            UPDATE alunos 
            SET nome = %s, cpf_rg = %s, endereco = %s, vencimento_mensalidade = %s, valor_mensalidade = %s, id_disciplina = %s, id_professor = %s
            WHERE id = %s;
        ''', (nome, cpf_rg, endereco, vencimento_mensalidade, valor_mensalidade, id_disciplina, id_professor, id_aluno))
        
        conn.commit()
        conn.close()
        return redirect('/alunos')

@app.route('/agenda', methods=['GET', 'POST'])
def agenda():
    # PROTEÇÃO: Se não estiver logado, chuta para a tela de login
    if 'professor_id' not in session:
        return redirect('/')

    conn = obter_conexao()
    cursor = conn.cursor()
    if is_sqlite_conn(conn):
        cursor.execute("PRAGMA foreign_keys = ON;")

    erro = None

    # 1. PROCESSAR AGENDAMENTO (POST)
    if request.method == 'POST':
        id_sala = request.form.get('id_sala')
        # SEGURANÇA: Em vez de pegar o id do professor do formulário, 
        # pegamos direto da sessão do cara que está logado!
        id_professor = session['professor_id']
        id_aluno = request.form.get('id_aluno')
        dia_semana = request.form.get('dia_semana')
        horario = request.form.get('horario')
        
        # NOVOS CAMPOS: Pegando as informações de tipo e data do formulário
        tipo_aula = request.form.get('tipo_aula', 'Fixa')
        data_aula = request.form.get('data_aula')
        
        # Se for aula fixa, limpa a data para não sujeirar o banco
        if tipo_aula == 'Fixa':
            data_aula = None

        try:
            # AJUSTE NO INSERT: Agora gravando tipo_aula e data_aula
            cursor.execute('''
                INSERT INTO agenda (id_sala, id_professor, id_aluno, dia_semana, horario, tipo_aula, data_aula)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                ''', (id_sala, id_professor, id_aluno, dia_semana, horario, tipo_aula, data_aula))
            conn.commit()
            conn.close()
            return redirect(f'/agenda?sala_id={id_sala}') # Volta mantendo a sala aberta
        except Exception:
            erro = "Conflito de Horário! A sala ou o professor já possuem aula agendada neste dia e horário."

    # 2. MONTAR A GRADE HORÁRIA (GET)
    sala_selecionada = request.args.get('sala_id', 1, type=int)

    cursor.execute("SELECT id, nome FROM salas;")
    all_salas = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM professores;")
    all_professores = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM alunos;")
    all_alunos = cursor.fetchall()

    # INTELIGÊNCIA DO FILTRO: Pegamos a data de hoje (Ex: '2026-05-18')
    data_hoje = datetime.now().strftime('%Y-%m-%d')

    # AJUSTE NO SELECT: Buscamos os agendamentos da sala conectando com Aluno e Professor,
    # mas aplicamos o filtro para ignorar Recuperações que já passaram de hoje!
    cursor.execute('''
        SELECT age.dia_semana, age.horario, al.nome, p.nome, d.nome, age.tipo_aula
        FROM agenda age
        JOIN alunos al ON age.id_aluno = al.id
        JOIN professores p ON age.id_professor = p.id
        JOIN disciplinas d ON al.id_disciplina = d.id
        WHERE age.id_sala = %s
        AND (age.tipo_aula = 'Fixa' OR (age.tipo_aula = 'Recuperacao' AND age.data_aula >= %s));
    ''', (sala_selecionada, data_hoje))
    agendamentos_banco = cursor.fetchall()

    # Mapear os agendamentos em um dicionário Python para busca rápida no HTML
    mapa_agenda = {}
    # Adicionamos 'tipo' no laço para capturar o tipo_aula vindo do banco
    for dia, hora, num_aluno, num_prof, num_curso, tipo in agendamentos_banco:
        hora_formatada = hora[:5]
        
        # --- LÓGICA DE OCULTAR RECUPERAÇÃO QUE JÁ PASSOU ---
        if tipo == 'Recuperacao':
            # Mapeamento para descobrir o dia de hoje em texto
            dias_semana_pt = {
                0: 'Segunda', 1: 'Terça', 2: 'Quarta',
                3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'
            }
            dia_hoje_pt = dias_semana_pt[datetime.now().weekday()]
            
            # Se a aula de recuperação for marcada para o dia de hoje
            if dia == dia_hoje_pt:
                hora_agora = datetime.now().strftime('%H:%M')
                # Se o relógio já passou da hora da aula (ex: 22:30 > 17:00), ignora e pula!
                if hora_agora > hora_formatada:
                    continue 

        # # TOQUE VISUAL EXTRA: Se for recuperação, adicionamos um aviso no texto da grade!
        # Descobre se o professor desta aula específica é o utilizador logado
        eh_minha_aula = (num_prof == session['professor_nome'])
        classe_destaque = "aula-minha-card" if eh_minha_aula else "aula-outra-card"

        if tipo == 'Recuperacao':
            texto_aula = f"🚨 [REC] {num_aluno} ({num_curso})"
        else:
            texto_aula = f"{num_aluno} ({num_curso})"
            
        # Adiciona o nome do professor em baixo apenas se não for tua, para poupar espaço visual
        if not eh_minha_aula:
            texto_aula += f" <br><small class='text-muted'>Prof. {num_prof}</small>"

        # Guardamos o conteúdo envelopado numa div com a classe correspondente
        mapa_agenda[(dia, hora_formatada)] = f"<div class='{classe_destaque}'>{texto_aula}</div>"
    # Estruturas fixas para a matriz
    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
    horarios_grade = [f"{h:02d}:00" for h in range(8, 22)] # Das 08:00 às 21:00

    conn.close() # Garante que fecha a conexão se passar pelo GET direto

    return render_template(
        'agenda.html', 
        salas=all_salas, 
        professores=all_professores, 
        alunos=all_alunos, 
        mapa_agenda=mapa_agenda, 
        dias_semana=dias_semana, 
        horarios=horarios_grade,
        sala_selecionada=sala_selecionada,
        erro=erro,
        id_professor_logado=session['professor_id'], # Enviando o ID do usuário atual
        nome_professor=session['professor_nome']
    )



# NOVA ROTA: Muda o status do aluno para Pago ou cancela a baixa
@app.route('/baixar_pagamento/<int:id>/<int:status_pago>')
def baixar_pagamento(id, status_pago):
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute("UPDATE alunos SET pago = %s WHERE id = %s;", (status_pago, id))
    conn.commit()
    conn.close()
    return redirect('/financeiro')

@app.route('/criar_senhas_professores')
def criar_senhas_professores():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    # FORÇA A CRIAÇÃO DAS COLUNAS CASO ELAS NÃO EXISTAM AINDA
    try:
        cursor.execute("ALTER TABLE professores ADD COLUMN login TEXT;")
        cursor.execute("ALTER TABLE professores ADD COLUMN senha TEXT;")
        conn.commit()
    except Exception:
        pass # Se as colunas já existirem, ignora o erro e segue em frente
        
    # Daqui para baixo continua o seu código normal...
    senha_padrao_hash = generate_password_hash('estudioa123')
    
    professores_config = {
        'Bruno Moura': 'bruno',
        'Bruno Mota': 'brunomota',
        'Raphael Russowsky': 'raphael',
        'Guilherme Martins': 'guilherme',
        'Beatriz Ribeiro': 'beatriz'
    }
    
    mensagens = []
    
    for nome_prof, login_prof in professores_config.items():
        # Verificamos se o professor existe no banco (usando LIKE para evitar problemas de acentuação)
        cursor.execute("SELECT id FROM professores WHERE nome LIKE %s;", (f"%{nome_prof}%",))
        resultado = cursor.fetchone()
        
        if resultado:
            id_prof = resultado[0]
            # Atualiza o login e a senha criptografada do professor
            cursor.execute('''
                UPDATE professores 
                SET login = %s, senha = %s 
                WHERE id = %s;
            ''', (login_prof, senha_padrao_hash, id_prof))
            mensagens.append(f"✅ Professor {nome_prof} atualizado! Login: {login_prof}")
        else:
            mensagens.append(f"❌ Professor {nome_prof} não foi encontrado no banco de dados.")
            
    conn.commit()
    conn.close()
    
    # Retorna um relatório simples na tela do navegador
    return "<br>".join(mensagens) + "<br><br><strong>Pronto! Todos os professores foram configurados com a senha padrão: estudioa123</strong>"
@app.route('/atualizar_banco_agenda')
def atualizar_banco_agenda():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    # Adiciona as novas colunas necessárias para a inteligência da agenda
    try:
        cursor.execute("ALTER TABLE agenda ADD COLUMN tipo_aula TEXT DEFAULT 'Fixa';")
        cursor.execute("ALTER TABLE agenda ADD COLUMN data_aula TEXT;")
        conn.commit()
        mensagem = "✅ Banco de dados atualizado com sucesso! Colunas 'tipo_aula' e 'data_aula' criadas."
    except Exception:
        mensagem = "⚠️ As colunas já existem ou o banco já estava atualizado."
        
    conn.close()
    return f"<h3>{mensagem}</h3><br><a href='/dashboard'>Voltar para o Dashboard</a>"

@app.route('/atualizar_banco_alunos')
def atualizar_banco_alunos():
    conn = obter_conexao()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN id_professor INTEGER REFERENCES professores(id);")
        conn.commit()
        mensagem = "✅ Tabela 'alunos' atualizada! Coluna 'id_professor' criada."
    except Exception:
        mensagem = "⚠️ A coluna 'id_professor' já existe na tabela de alunos."
    conn.close()
    return f"<h3>{mensagem}</h3><br><a href='/dashboard'>Voltar para o Dashboard</a>"

@app.route('/aluno/contrato/<int:id_aluno>')
def gerar_contrato_aluno(id_aluno):
    if 'professor_id' not in session:
        return redirect('/')

    conn = obter_conexao()
    cursor = conn.cursor()
    
    # Adicionámos cpf_rg, endereco e dia_vencimento no SELECT
    cursor.execute('''
        SELECT al.id, al.nome, al.id_disciplina, d.nome, al.valor_mensalidade, al.cpf_rg, al.endereco, al.dia_vencimento
        FROM alunos al
        JOIN disciplinas d ON al.id_disciplina = d.id
        WHERE al.id = %s;
    ''', (id_aluno,))
    
    aluno_dados = cursor.fetchone()
    conn.close()

    if not aluno_dados:
        return "Aluno não encontrado!", 404

    return render_template('contrato.html', aluno=aluno_dados)

@app.route('/atualizar_banco_contrato_completo')
def atualizar_banco_contrato_completo():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    mensagens = []
    
    # Tenta adicionar cpf_rg (caso não exista)
    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN cpf_rg TEXT;")
        mensagens.append("✅ Coluna 'cpf_rg' criada.")
    except Exception:
        mensagens.append("⚠️ Coluna 'cpf_rg' já existia.")
        
    # Tenta adicionar endereco
    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN endereco TEXT;")
        mensagens.append("✅ Coluna 'endereco' criada.")
    except Exception:
        mensagens.append("⚠️ Coluna 'endereco' já existia.")
        
    # Tenta adicionar dia_vencimento
    try:
        cursor.execute("ALTER TABLE alunos ADD COLUMN dia_vencimento INTEGER;")
        mensagens.append("✅ Coluna 'dia_vencimento' criada.")
    except Exception:
        mensagens.append("⚠️ Coluna 'dia_vencimento' já existia.")
        
    conn.commit()
    conn.close()
    
    resultado = "<br>".join(mensagens)
    return f"<h3>Status da Migração:</h3><p>{resultado}</p><br><a href='/alunos'>Ir para Alunos</a>"


@app.route('/financeiro', methods=['GET', 'POST'])
def financeiro():
    if 'professor_id' not in session:
        return redirect('/')
        
    nome_logado = session['professor_nome']
    
    # 1. PEGAR A COMPETÊNCIA (Se o usuário filtrou, usa o do formulário. Se não, usa o mês atual)
    if request.method == 'POST' and request.form.get('competencia_filtro'):
        competencia_atual = request.form.get('competencia_filtro')
    else:
        competencia_atual = datetime.now().strftime('%m/%Y')

    conn = obter_conexao()
    cursor = conn.cursor()

    # --- GERADOR AUTOMÁTICO DE MENSALIDADES ---
    # Só gera mensalidades automaticamente se for o mês corrente (para não bagunçar o histórico)
    if competencia_atual == datetime.now().strftime('%m/%Y'):
        cursor.execute("SELECT id, valor_mensalidade FROM alunos;")
        all_alunos = cursor.fetchall()
        
        for id_aluno, valor in all_alunos:
            cursor.execute("SELECT id FROM mensalidades WHERE id_aluno = %s AND competencia = %s;", (id_aluno, competencia_atual))
            existe = cursor.fetchone()
            if not existe:
                cursor.execute('''
                    INSERT INTO mensalidades (id_aluno, competencia, valor_devido, status)
                        VALUES (%s, %s, %s, 'Pendente');
                    ''', (id_aluno, competencia_atual, valor))
        conn.commit()

    # --- LISTAR OS MESES DISPONÍVEIS PARA O SELETOR (Histórico de cobranças existentes) ---
    cursor.execute("SELECT DISTINCT competencia FROM mensalidades ORDER BY id DESC;")
    meses_disponiveis = [row[0] for row in cursor.fetchall()]
    
    # Garante que o mês atual sempre esteja na lista do seletor
    if datetime.now().strftime('%m/%Y') not in meses_disponiveis:
        meses_disponiveis.insert(0, datetime.now().strftime('%m/%Y'))

    # --- BUSCAR AS MENSALIDADES DA COMPETÊNCIA ESCOLHIDA ---
    if nome_logado == 'Bruno Moura':
        cursor.execute('''
            SELECT m.id, al.nome, m.competencia, m.valor_devido, m.status, m.data_pagamento, d.nome
            FROM mensalidades m
            JOIN alunos al ON m.id_aluno = al.id
            JOIN disciplinas d ON al.id_disciplina = d.id
            WHERE m.competencia = %s;
        ''', (competencia_atual,))
    else:
        cursor.execute('''
            SELECT m.id, al.nome, m.competencia, m.valor_devido, m.status, m.data_pagamento, d.nome
            FROM mensalidades m
            JOIN alunos al ON m.id_aluno = al.id
            JOIN disciplinas d ON al.id_disciplina = d.id
            WHERE m.competencia = %s AND al.id_professor = %s;
        ''', (competencia_atual, session['professor_id']))
        
    lista_mensalidades = cursor.fetchall()
    conn.close()

    return render_template(
        'financeiro.html', 
        mensalidades=lista_mensalidades, 
        competencia=competencia_atual,
        meses_opcoes=meses_disponiveis
    )

@app.route('/financeiro/pagar/<int:id_mensalidade>')
def pagar_mensalidade(id_mensalidade):
    if 'professor_id' not in session:
        return redirect('/')

    data_hoje = datetime.now().strftime('%d/%m/%Y')

    conn = obter_conexao()
    cursor = conn.cursor()
    
    # Atualiza o status e insere a data do pagamento
    cursor.execute('''
        UPDATE mensalidades 
        SET status = 'Pago', data_pagamento = %s 
        WHERE id = %s;
    ''', (data_hoje, id_mensalidade))
    
    conn.commit()
    conn.close()
    
    return redirect('/financeiro')

if __name__ == '__main__':
    try:
        init_db()
        aplicar_migracoes()
        popular_dados_iniciais()
    except Exception as e:
        print('Aviso: falha na inicialização do banco:', e)

    import os
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta)


    