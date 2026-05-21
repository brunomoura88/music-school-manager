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
    url_banco = os.environ.get("DATABASE_URL")
    
    if url_banco:
        import psycopg
        from psycopg.rows import dict_row
        
        url_banco = url_banco.strip()
        if url_banco.startswith("postgres://"):
            url_banco = url_banco.replace("postgres://", "postgresql://", 1)
            
        return psycopg.connect(url_banco, row_factory=dict_row)
    else:
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

# --- INICIALIZAÇÃO DO APP E CONFIGURAÇÃO DE SESSÃO CRUCIAL ---
app = Flask(__name__)

# Secret key protegida por variável de ambiente
app.secret_key = os.environ.get("SECRET_KEY", "EstudioA_ChaveSecreta_Chaveirao_123!")

# Ajuste de Cookies aplicado IMEDIATAMENTE após a criação do app
if os.environ.get("DATABASE_URL"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )
else:
    app.config.update(
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
    )

# ==========================================
# ROTAS DO SISTEMA
# ==========================================

@app.route('/bypass-login')
def bypass_login():
    session['professor_id'] = 1  
    session['professor_nome'] = 'Bruno Moura'
    session.modified = True
    return redirect('/dashboard')

@app.route('/reset-professores-estudioa')
def reset_professores():
    conn = obter_conexao()
    cursor = conn.cursor()
    
    try:
        # 1. Deleta a tabela antiga para eliminar qualquer lixo acumulado
        cursor.execute("DROP TABLE IF EXISTS professores CASCADE;")
        conn.commit()
        
        is_postgres = hasattr(conn, 'encoding') or conn.__class__.__name__ == 'Connection'
        id_auto = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        
        # 2. Recria a tabela FORÇANDO as colunas login e cpf a serem UNIQUE reais no banco
        cursor.execute(f'''
            CREATE TABLE professores (
                id {id_auto},
                nome VARCHAR(255) NOT NULL,
                cpf VARCHAR(255) UNIQUE NOT NULL,
                login VARCHAR(255) UNIQUE NOT NULL,
                senha VARCHAR(255) NOT NULL
            );
        ''')
        conn.commit()
        
        # 3. Gera um hash limpo e direto
        senha_criptografada = generate_password_hash('estudioa123')
        
        # 4. Insere o seu administrador absoluto com ID fixo 1
        cursor.execute('''
            INSERT INTO professores (id, nome, cpf, login, senha) 
            VALUES (1, %s, %s, %s, %s);
        ''', ('Bruno Moura', '123', 'bruno', senha_criptografada))
        conn.commit()
        
        mensagem = "✅ SUCESSO ABSOLUTO! Tabela recriada. Usuário único 'bruno' pronto com a senha 'estudioa123'."
    except Exception as e:
        mensagem = f"❌ Erro crítico no reset: {str(e)}"
    finally:
        cursor.close()
        conn.close()
        
    return f"<h3>{mensagem}</h3><br><a href='/'>Ir para o Login</a>"

@app.route('/', methods=['GET', 'POST'])
def login():
    erro = None

    if request.method == 'POST':
        conn = None
        cursor = None
        try:
            usuario_input = request.form.get('cpf')
            if not usuario_input:
                usuario_input = request.form.get('login')
                
            senha_input = request.form.get('senha')

            if usuario_input:
                usuario_input = usuario_input.strip()

            conn = obter_conexao()
            cursor = conn.cursor()

            cursor.execute("SELECT id, nome, senha FROM professores WHERE login = %s OR cpf = %s;", (usuario_input, usuario_input))
            professor = cursor.fetchone()

            if professor:
                # Extração Blindada: Funciona para Dicionário (Postgres), Row (SQLite) ou Tupla
                if isinstance(professor, dict):
                    id_prof = professor.get('id')
                    nome_prof = professor.get('nome')
                    senha_banco = professor.get('senha')
                elif hasattr(professor, 'keys'): # Se for o objeto Row do SQLite
                    id_prof = professor['id']
                    nome_prof = professor['nome']
                    senha_banco = professor['senha']
                else: # Se por acaso voltar como tupla pura
                    id_prof, nome_prof, senha_banco = professor
                
                # Agora sim o teste da senha acontece sem desvios
                if senha_banco == senha_input or (senha_banco and senha_banco.startswith(('scrypt:', 'pbkdf2:')) and check_password_hash(senha_banco, senha_input)):
                    
                    if senha_banco == senha_input:
                        senha_com_hash = generate_password_hash(senha_input)
                        cursor.execute("UPDATE professores SET senha = %s WHERE id = %s;", (senha_com_hash, id_prof))
                        conn.commit()

                    session['professor_id'] = id_prof
                    session['professor_nome'] = str(nome_prof)
                    session.modified = True 
                    
                    return redirect('/dashboard')
                else:
                    erro = "Senha incorreta!"
            else:
                erro = f"Usuário '{usuario_input}' não encontrado."
                
        except Exception as e:
            # Se der qualquer erro no desempacotamento, nós vamos forçar a exibição no terminal do Render
            print(f"❌ ERRO CRÍTICO NO FLUXO DE LOGIN: {str(e)}")
            erro = f"Erro no processamento interno: {str(e)}"
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template('login.html', erro=erro)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'professor_id' not in session:
        return redirect('/')

    id_logado = session['professor_id']
    nome_logado = session['professor_nome']

    conn = obter_conexao()
    cursor = conn.cursor()

    if nome_logado == 'Bruno Moura':
        cursor.execute("SELECT COUNT(*) AS total FROM alunos;")
    else:
        cursor.execute("SELECT COUNT(*) AS total FROM alunos WHERE id_professor = %s;", (id_logado,))
    
    resultado_alunos = cursor.fetchone()
    
    if isinstance(resultado_alunos, dict):
        total_alunos = resultado_alunos['total']
    else:
        total_alunos = resultado_alunos[0] if resultado_alunos else 0

    dias_semana_pt = {
        0: 'Segunda', 1: 'Terça', 2: 'Quarta',
        3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'
    }
    dia_atual_num = datetime.now().weekday()
    dia_atual_pt = dias_semana_pt[dia_atual_num]

    if nome_logado == 'Bruno Moura':
        cursor.execute("SELECT COUNT(*) AS total FROM agenda WHERE dia_semana = %s;", (dia_atual_pt,))
    else:
        cursor.execute("SELECT COUNT(*) AS total FROM agenda WHERE dia_semana = %s AND id_professor = %s;", (dia_atual_pt, id_logado))
        
    resultado_aulas = cursor.fetchone()
    
    if isinstance(resultado_aulas, dict):
        aulas_hoje = resultado_aulas['total']
    else:
        aulas_hoje = resultado_aulas[0] if resultado_aulas else 0

    cursor.close()
    conn.close()

    meses_ano = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    mes_atual = meses_ano[datetime.now().month - 1]
    ano_atual = datetime.now().year
    competencia_atual = f"{mes_atual}/{ano_atual}"

    return render_template(
        'dashboard.html', 
        nome_professor=nome_logado,
        total_alunos=total_alunos,
        aulas_hoje=aulas_hoje,
        competencia=competencia_atual
    )

@app.route('/alunos', methods=['GET', 'POST'])
def alunos():
    if 'professor_id' not in session:
        return redirect('/')

    id_logado = session['professor_id']
    nome_logado = session['professor_nome']

    conn = obter_conexao()
    cursor = conn.cursor()

    if request.method == 'POST':
        nome = request.form.get('nome')
        cpf = request.form.get('cpf')
        telefone = request.form.get('telefone')
        instrumento = request.form.get('instrumento')
        dia_aula = request.form.get('dia_aula')
        horario_aula = request.form.get('horario_aula')
        id_disciplina = request.form.get('id_disciplina')
        valor_mensalidade = request.form.get('valor')
        dia_semana = request.form.get('dia_semana') 
        
        cpf_rg = request.form.get('cpf_rg') if request.form.get('cpf_rg') else request.form.get('cpf')
        endereco = request.form.get('endereco')
        dia_vencimento = request.form.get('dia_vencimento')
        
        id_professor_vinc = id_logado 

        cursor.execute('''
            INSERT INTO alunos (nome, id_disciplina, valor_mensalidade, dia_semana, id_professor, cpf_rg, endereco, dia_vencimento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        ''', (nome, id_disciplina, valor_mensalidade, dia_semana, id_professor_vinc, cpf_rg, endereco, dia_vencimento))
        
        conn.commit()
        conn.close() 
        return redirect('/alunos')

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

    cursor.execute("SELECT id, nome FROM disciplinas;")
    disciplinas_lista = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM professores;")
    professores_lista = cursor.fetchall()

    conn.close()
    return render_template('alunos.html', alunos=alunos_lista, disciplinas=disciplinas_lista, professores=professores_lista)

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

    if request.method == 'GET':
        cursor.execute('''
            SELECT id, nome, cpf_rg, endereco, vencimento_mensalidade, valor_mensalidade, id_disciplina, id_professor 
            FROM alunos 
            WHERE id = %s;
        ''', (id_aluno,))
        aluno_dados = cursor.fetchone()

        if not aluno_dados:
            conn.close()
            return "Aluno não encontrado!", 404

        cursor.execute("SELECT id, nome FROM disciplinas;")
        disciplinas_lista = cursor.fetchall()

        cursor.execute("SELECT id, nome FROM professores;")
        professores_lista = cursor.fetchall()

        conn.close()
        return render_template('editar_aluno.html', aluno=aluno_dados, disciplinas=disciplinas_lista, professores=professores_lista)

    elif request.method == 'POST':
        nome = request.form.get('nome')
        cpf_rg = request.form.get('cpf')
        endereco = request.form.get('endereco')
        vencimento_mensalidade = request.form.get('dia_vencimento')
        valor_mensalidade = request.form.get('valor')
        id_disciplina = request.form.get('id_disciplina')
        id_professor = request.form.get('id_professor')

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
    if 'professor_id' not in session:
        return redirect('/')

    conn = obter_conexao()
    cursor = conn.cursor()
    if is_sqlite_conn(conn):
        cursor.execute("PRAGMA foreign_keys = ON;")

    erro = None

    if request.method == 'POST':
        id_sala = request.form.get('id_sala')
        id_professor = session['professor_id']
        id_aluno = request.form.get('id_aluno')
        dia_semana = request.form.get('dia_semana')
        horario = request.form.get('horario')
        
        type_aula_val = request.form.get('tipo_aula', 'Fixa')
        data_aula = request.form.get('data_aula')
        
        if type_aula_val == 'Fixa':
            data_aula = None

        try:
            cursor.execute('''
                INSERT INTO agenda (id_sala, id_professor, id_aluno, dia_semana, horario, tipo_aula, data_aula)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                ''', (id_sala, id_professor, id_aluno, dia_semana, horario, type_aula_val, data_aula))
            conn.commit()
            conn.close()
            return redirect(f'/agenda?sala_id={id_sala}')
        except Exception:
            erro = "Conflito de Horário!"

    sala_selecionada = request.args.get('sala_id', 1, type=int)

    cursor.execute("SELECT id, nome FROM salas;")
    all_salas = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM professores;")
    all_professores = cursor.fetchall()

    cursor.execute("SELECT id, nome FROM alunos;")
    all_alunos = cursor.fetchall()

    data_hoje = datetime.now().strftime('%Y-%m-%d')

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

    mapa_agenda = {}
    for row in agendamentos_banco:
        if isinstance(row, dict):
            dia, hora, num_aluno, num_prof, num_curso, tipo = row['dia_semana'], row['horario'], row['nome'], row[3], row[4], row['tipo_aula']
        else:
            dia, hora, num_aluno, num_prof, num_curso, tipo = row[0], row[1], row[2], row[3], row[4], row[5]
            
        hora_formatada = hora[:5]
        
        if tipo == 'Recuperacao':
            dias_semana_pt = {0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'}
            dia_hoje_pt = dias_semana_pt[datetime.now().weekday()]
            if dia == dia_hoje_pt:
                hora_agora = datetime.now().strftime('%H:%M')
                if hora_agora > hora_formatada:
                    continue 

        eh_minha_aula = (num_prof == session['professor_nome'])
        classe_destaque = "aula-minha-card" if eh_minha_aula else "aula-outra-card"

        if tipo == 'Recuperacao':
            texto_aula = f"🚨 [REC] {num_aluno} ({num_curso})"
        else:
            texto_aula = f"{num_aluno} ({num_curso})"
            
        if not eh_minha_aula:
            texto_aula += f" <br><small class='text-muted'>Prof. {num_prof}</small>"

        mapa_agenda[(dia, hora_formatada)] = f"<div class='{classe_destaque}'>{texto_aula}</div>"

    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
    horarios_grade = [f"{h:02d}:00" for h in range(8, 22)] 

    conn.close()
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
        id_professor_logado=session['professor_id'], 
        nome_professor=session['professor_nome']
    )

@app.route('/baixar_pagamento/<int:id>/<int:status_pago>')
def baixar_pagamento(id, status_pago):
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute("UPDATE alunos SET pago = %s WHERE id = %s;", (status_pago, id))
    conn.commit()
    conn.close()
    return redirect('/financeiro')

@app.route('/aluno/contrato/<int:id_aluno>')
def gerar_contrato_aluno(id_aluno):
    if 'professor_id' not in session:
        return redirect('/')

    conn = obter_conexao()
    cursor = conn.cursor()
    
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

@app.route('/financeiro', methods=['GET', 'POST'])
def financeiro():
    if 'professor_id' not in session:
        return redirect('/')
        
    nome_logado = session['professor_nome']
    
    if request.method == 'POST' and request.form.get('competencia_filtro'):
        competencia_atual = request.form.get('competencia_filtro')
    else:
        competencia_atual = datetime.now().strftime('%m/%Y')

    conn = obter_conexao()
    cursor = conn.cursor()

    if competencia_atual == datetime.now().strftime('%m/%Y'):
        cursor.execute("SELECT id, valor_mensalidade FROM alunos;")
        all_alunos = cursor.fetchall()
        
        for aluno in all_alunos:
            if isinstance(aluno, dict):
                id_aluno, valor = aluno['id'], aluno['valor_mensalidade']
            else:
                id_aluno, valor = aluno[0], aluno[1]
                
            cursor.execute("SELECT id FROM mensalidades WHERE id_aluno = %s AND competencia = %s;", (id_aluno, competencia_atual))
            existe = cursor.fetchone()
            if not existe:
                cursor.execute('''
                    INSERT INTO mensalidades (id_aluno, competencia, valor_devido, status)
                        VALUES (%s, %s, %s, 'Pendente');
                    ''', (id_aluno, competencia_atual, valor))
        conn.commit()

    cursor.execute("SELECT DISTINCT competencia FROM mensalidades ORDER BY id DESC;")
    meses_banco = cursor.fetchall()
    
    meses_disponiveis = []
    for r in meses_banco:
        if isinstance(r, dict):
            meses_disponiveis.append(r['competencia'])
        else:
            meses_disponiveis.append(r[0])
    
    if datetime.now().strftime('%m/%Y') not in meses_disponiveis:
        meses_disponiveis.insert(0, datetime.now().strftime('%m/%Y'))

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
    
    cursor.execute('''
        UPDATE mensalidades 
        SET status = 'Pago', data_pagamento = %s 
        WHERE id = %s;
    ''', (data_hoje, id_mensalidade))
    
    conn.commit()
    conn.close()
    return redirect('/financeiro')

if __name__ == '__main__':
    # Criamos uma checagem: se o app ligar, ele força a criação das tabelas no Supabase
    try:
        conn = obter_conexao()
        cursor = conn.cursor()
        
        is_postgres = hasattr(conn, 'encoding') or conn.__class__.__name__ == 'Connection'
        id_auto = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        text_type = "VARCHAR(255)" if is_postgres else "TEXT"
        real_type = "NUMERIC(10,2)" if is_postgres else "REAL"
        
        # Garante que a tabela de professores exista
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS professores (
                id {id_auto},
                nome {text_type} NOT NULL,
                cpf {text_type} UNIQUE NOT NULL,
                login {text_type},
                senha {text_type}
            );
        ''')
        
        # Garante que a tabela de alunos exista para a dashboard não quebrar
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS alunos (
                id {id_auto},
                nome {text_type} NOT NULL,
                id_professor INTEGER,
                valor_mensalidade {real_type},
                vencimento_mensalidade {text_type}
            );
        ''')
        
        # Garante que a tabela de agenda exista para a dashboard não quebrar
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS agenda (
                id {id_auto},
                dia_semana {text_type} NOT NULL,
                horario {text_type} NOT NULL,
                id_professor INTEGER,
                id_aluno INTEGER,
                tipo_aula {text_type} DEFAULT 'Regular',
                data_aula {text_type}
            );
        ''')
        
        # Insere o seu usuário administrador caso ele não exista no Supabase
        cursor.execute("SELECT id FROM professores WHERE login = 'bruno';")
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO professores (nome, cpf, login, senha) 
                VALUES (%s, %s, %s, %s);
            ''', ('Bruno Moura', '123', 'bruno', generate_password_hash('estudioa123')))
            
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Banco de dados sincronizado com sucesso no Supabase!")
    except Exception as e:
        print('Aviso: falha na inicialização forçada do banco:', e)

    import os
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta)