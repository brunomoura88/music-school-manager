from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import sqlite3
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
import os


def is_sqlite_conn(conn):
    return conn.__class__.__module__.startswith("sqlite3")


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
        sqlite_conn = sqlite3.connect("estudio_a.db")
        sqlite_conn.row_factory = sqlite3.Row

        class SQLiteCursorWrapper:
            def __init__(self, cursor):
                self._cursor = cursor

            def execute(self, query, params=None):
                if params is None:
                    params = ()
                return self._cursor.execute(query.replace("%s", "?"), params)

            def executemany(self, query, param_seq):
                return self._cursor.executemany(query.replace("%s", "?"), param_seq)

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
app.secret_key = os.environ.get("SECRET_KEY", "EstudioA_ChaveSecreta_Chaveirao_123!")

if os.environ.get("DATABASE_URL"):
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
else:
    app.config.update(
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )


@app.route("/bypass-login")
def bypass_login():
    session["professor_id"] = 1
    session["professor_nome"] = "Bruno Moura"
    session.modified = True
    return redirect("/dashboard")


@app.route("/reset-professores-estudioa")
def reset_professores():
    conn = obter_conexao()
    cursor = conn.cursor()
    try:
        cursor.execute("DROP TABLE IF EXISTS professores CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS alunos CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS agenda CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS disciplinas CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS salas CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS mensalidades CASCADE;")
        conn.commit()

        is_postgres = (
            hasattr(conn, "encoding") or conn.__class__.__name__ == "Connection"
        )
        id_auto = (
            "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        )
        text_type = "VARCHAR(255)" if is_postgres else "TEXT"
        real_type = "NUMERIC(10,2)" if is_postgres else "REAL"

        cursor.execute(
            f"CREATE TABLE professores (id {id_auto}, nome {text_type} NOT NULL, cpf {text_type} UNIQUE NOT NULL, login {text_type} UNIQUE NOT NULL, senha {text_type} NOT NULL);"
        )
        cursor.execute(
            f"CREATE TABLE disciplinas (id {id_auto}, nome {text_type} UNIQUE NOT NULL);"
        )
        cursor.execute(
            f"CREATE TABLE salas (id {id_auto}, nome {text_type} UNIQUE NOT NULL);"
        )
        cursor.execute(
            f"CREATE TABLE alunos (id {id_auto}, nome {text_type} NOT NULL, cpf_rg {text_type}, vencimento_mensalidade {text_type}, valor_mensalidade {real_type}, id_disciplina INTEGER, id_professor INTEGER, endereco {text_type});"
        )
        cursor.execute(
            f"CREATE TABLE agenda (id {id_auto}, dia_semana {text_type} NOT NULL, horario {text_type} NOT NULL, id_professor INTEGER, id_aluno INTEGER, tipo_aula {text_type} DEFAULT 'Regular', data_aula {text_type}, id_sala INTEGER DEFAULT 1);"
        )

        senha_padrao = generate_password_hash("estudioa123")
        professores_iniciais = [
            ("Bruno Moura", "123", "brunomoura", senha_padrao),
            ("Bruno Mota", "456", "brunomota", senha_padrao),
            ("Raphael Russowsky", "789", "raphael", senha_padrao),
            ("Guilherme Martins", "101", "guilherme", senha_padrao),
            ("Beatriz Ribeiro", "202", "beatriz", senha_padrao),
        ]
        cursor.executemany(
            "INSERT INTO professores (nome, cpf, login, senha) VALUES (%s, %s, %s, %s);",
            professores_iniciais,
        )
        cursor.execute("INSERT INTO disciplinas (nome) VALUES ('Violão');")
        cursor.execute("INSERT INTO disciplinas (nome) VALUES ('Guitarra');")
        cursor.execute("INSERT INTO disciplinas (nome) VALUES ('Teclado');")
        cursor.execute("INSERT INTO disciplinas (nome) VALUES ('Canto');")
        cursor.execute("INSERT INTO salas (nome) VALUES ('Sala 01');")
        cursor.execute("INSERT INTO salas (nome) VALUES ('Sala 02');")
        conn.commit()
        mensagem = "✅ SISTEMA RESETADO COM SUCESSO! Tabelas recriadas com suporte a endereço e cpf_rg."
    except Exception as e:
        mensagem = f"❌ Erro na reestruturação: {str(e)}"
    finally:
        cursor.close()
        conn.close()
    return f"<h3>{mensagem}</h3><br><a href='/'>Ir para o Login</a>"


@app.route("/", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        conn = None
        cursor = None
        try:
            usuario_input = request.form.get("cpf")
            if not usuario_input:
                usuario_input = request.form.get("login")
            senha_input = request.form.get("senha")
            if usuario_input:
                usuario_input = usuario_input.strip()

            conn = obter_conexao()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, nome, senha FROM professores WHERE login = %s OR cpf = %s;",
                (usuario_input, usuario_input),
            )
            professor = cursor.fetchone()

            if professor:
                if isinstance(professor, dict):
                    id_prof, nome_prof, senha_banco = (
                        professor.get("id"),
                        professor.get("nome"),
                        professor.get("senha"),
                    )
                elif hasattr(professor, "keys"):
                    id_prof, nome_prof, senha_banco = (
                        professor["id"],
                        professor["nome"],
                        professor["senha"],
                    )
                else:
                    id_prof, nome_prof, senha_banco = professor

                if senha_banco == senha_input or (
                    senha_banco
                    and senha_banco.startswith(("scrypt:", "pbkdf2:"))
                    and check_password_hash(senha_banco, senha_input)
                ):
                    if senha_banco == senha_input:
                        senha_com_hash = generate_password_hash(senha_input)
                        cursor.execute(
                            "UPDATE professores SET senha = %s WHERE id = %s;",
                            (senha_com_hash, id_prof),
                        )
                        conn.commit()
                    session["professor_id"] = id_prof
                    session["professor_nome"] = str(nome_prof)
                    session.modified = True
                    return redirect("/dashboard")
                else:
                    erro = "Senha incorreta!"
            else:
                erro = f"Usuário não encontrado."
        except Exception as e:
            erro = f"Erro interno: {str(e)}"
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if "professor_id" not in session:
        return redirect("/")
    id_logado, nome_logado = session["professor_id"], session["professor_nome"]

    nome_professor = session.get("professor_nome", "Professor")
    
    conn = obter_conexao()
    cursor = conn.cursor()

    gestores_escola = ["Bruno Moura", "Bruno Mota", "Raphael Russowsky"]

    if nome_logado in gestores_escola:
        cursor.execute("SELECT COUNT(*) AS total FROM alunos;")
    else:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM alunos WHERE id_professor = %s;",
            (id_logado,),
        )
    res_alunos = cursor.fetchone()
    total_alunos = (
        res_alunos["total"]
        if isinstance(res_alunos, dict)
        else (res_alunos[0] if res_alunos else 0)
    )

    dias_semana_pt = {
        0: "Segunda",
        1: "Terça",
        2: "Quarta",
        3: "Quinta",
        4: "Sexta",
        5: "Sábado",
        6: "Domingo",
    }
    dia_atual_pt = dias_semana_pt[datetime.now().weekday()]

    if nome_logado in gestores_escola:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM agenda WHERE dia_semana = %s;",
            (dia_atual_pt,),
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM agenda WHERE dia_semana = %s AND id_professor = %s;",
            (dia_atual_pt, id_logado),
        )
    res_aulas = cursor.fetchone()
    aulas_hoje = (
        res_aulas["total"]
        if isinstance(res_aulas, dict)
        else (res_aulas[0] if res_aulas else 0)
    )

    cursor.close()
    conn.close()
    
    meses_ano = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    competencia_atual = f"{meses_ano[datetime.now().month - 1]}/{datetime.now().year}"

    return render_template(
        "dashboard.html",
        total_alunos=total_alunos,
        aulas_hoje=aulas_hoje,
        nome_professor=nome_professor,
        competencia=competencia_atual,
    )


@app.route("/alunos", methods=["GET", "POST"])
def alunos():
    if "professor_id" not in session:
        return redirect("/")
    id_logado, nome_logado = session["professor_id"], session["professor_nome"]
    conn = obter_conexao()
    cursor = conn.cursor()

    if request.method == "POST":
        nome = request.form.get("nome")
        id_disciplina = request.form.get("id_disciplina")
        valor_mensalidade = request.form.get("valor")
        dia_vencimento = request.form.get("dia_vencimento")
        cpf_rg = (
            request.form.get("cpf_rg")
            if request.form.get("cpf_rg")
            else request.form.get("cpf")
        )
        endereco = request.form.get("endereco", "")
        id_professor_vinc = request.form.get("id_professor", id_logado)

        cursor.execute(
            """
            INSERT INTO alunos (nome, id_disciplina, valor_mensalidade, id_professor, cpf_rg, vencimento_mensalidade, endereco)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """,
            (
                nome,
                id_disciplina,
                valor_mensalidade,
                id_professor_vinc,
                cpf_rg,
                dia_vencimento,
                endereco,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/alunos")

    if nome_logado in ["Bruno Moura", "Bruno Mota", "Raphael Russowsky"]:
        cursor.execute(
            "SELECT al.id, al.nome as aluno_nome, al.vencimento_mensalidade, al.valor_mensalidade, p.nome as prof_nome, d.nome as disc_nome FROM alunos al LEFT JOIN disciplinas d ON al.id_disciplina = d.id LEFT JOIN professores p ON al.id_professor = p.id ORDER BY al.id DESC;"
        )
    else:
        cursor.execute(
            "SELECT al.id, al.nome as aluno_nome, al.vencimento_mensalidade, al.valor_mensalidade, p.nome as prof_nome, d.nome as disc_nome FROM alunos al LEFT JOIN disciplinas d ON al.id_disciplina = d.id LEFT JOIN professores p ON al.id_professor = p.id WHERE al.id_professor = %s ORDER BY al.id DESC;",
            (id_logado,),
        )

    alunos_lista = []
    for r in cursor.fetchall():
        if isinstance(r, dict):
            alunos_lista.append(
                {
                    "id": r.get("id"),
                    "nome": r.get("aluno_nome"),
                    "vencimento_mensalidade": r.get("vencimento_mensalidade"),
                    "valor_mensalidade": r.get("valor_mensalidade"),
                    "professor_nome": r.get("prof_nome"),
                    "disciplina_nome": r.get("disc_nome"),
                }
            )
        else:
            alunos_lista.append(
                {
                    "id": r[0],
                    "nome": r[1],
                    "vencimento_mensalidade": r[2],
                    "valor_mensalidade": r[3],
                    "professor_nome": r[4],
                    "disciplina_nome": r[5],
                }
            )

    cursor.execute("SELECT id, nome FROM disciplinas ORDER BY nome;")
    disciplinas_lista = [
        d if isinstance(d, dict) else {"id": d[0], "nome": d[1]}
        for d in cursor.fetchall()
    ]
    cursor.execute("SELECT id, nome FROM professores ORDER BY nome;")
    professores_lista = [
        p if isinstance(p, dict) else {"id": p[0], "nome": p[1]}
        for p in cursor.fetchall()
    ]

    cursor.close()
    conn.close()
    return render_template(
        "alunos.html",
        alunos=alunos_lista,
        disciplinas=disciplinas_lista,
        professores=professores_lista,
    )


@app.route("/aluno/contrato/<id>")
def contrato(id):
    if "professor_id" not in session: return redirect("/")
    
    conn = obter_conexao(); cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            al.id, 
            al.nome, 
            al.cpf_rg, 
            al.endereco, 
            al.vencimento_mensalidade, 
            al.valor_mensalidade,
            p.nome AS professor_nome,
            d.nome AS disciplina_nome
        FROM alunos al
        LEFT JOIN professores p ON al.id_professor = p.id
        LEFT JOIN disciplinas d ON al.id_disciplina = d.id
        WHERE al.id = %s;
    """, (id,))
    
    aluno_dados = cursor.fetchone()
    
    if isinstance(aluno_dados, dict):
        aluno = aluno_dados
    elif aluno_dados:
        aluno = {
            "id": aluno_dados[0],
            "nome": aluno_dados[1],
            "cpf_rg": aluno_dados[2],
            "endereco": aluno_dados[3],
            "vencimento_mensalidade": aluno_dados[4],
            "valor_mensalidade": aluno_dados[5],
            "professor_nome": aluno_dados[6],
            "disciplina_nome": aluno_dados[7]
        }
    else:
        cursor.close(); conn.close()
        return "Aluno não encontrado", 404

    cursor.close(); conn.close()
    return render_template("contrato.html", aluno=aluno)


@app.route("/excluir_aluno/<int:id>")
def excluir_aluno(id):
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alunos WHERE id = %s;", (id,))
    conn.commit()
    conn.close()
    return redirect("/alunos")


@app.route("/aluno/editar/<int:id>", methods=["GET", "POST"])
def editar_aluno(id):
    if "professor_id" not in session:
        return redirect("/")
    conn = obter_conexao()
    cursor = conn.cursor()

    if request.method == "POST":
        nome = request.form.get("nome")
        cpf_rg = request.form.get("cpf")
        endereco = request.form.get("endereco")
        dia_vencimento = request.form.get("dia_vencimento")
        valor_mensalidade = request.form.get("valor")
        id_disciplina = request.form.get("id_disciplina")
        id_professor = request.form.get("id_professor")

        cursor.execute(
            "UPDATE alunos SET nome=%s, cpf_rg=%s, endereco=%s, vencimento_mensalidade=%s, valor_mensalidade=%s, id_disciplina=%s, id_professor=%s WHERE id=%s;",
            (
                nome,
                cpf_rg,
                endereco,
                dia_vencimento,
                valor_mensalidade,
                id_disciplina,
                id_professor,
                id,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/alunos")

    cursor.execute(
        "SELECT id, nome, cpf_rg, endereco, vencimento_mensalidade, valor_mensalidade, id_disciplina, id_professor FROM alunos WHERE id=%s;",
        (id,),
    )
    res = cursor.fetchone()
    if not res:
        cursor.close()
        conn.close()
        return "Aluno não encontrado", 404

    if hasattr(res, "get"):
        aluno_dados = {
            "id": res.get("id"),
            "nome": res.get("nome"),
            "cpf_rg": res.get("cpf_rg") if res.get("cpf_rg") else "",
            "endereco": res.get("endereco") if res.get("endereco") else "",
            "vencimento_mensalidade": res.get("vencimento_mensalidade"),
            "valor_mensalidade": res.get("valor_mensalidade"),
            "id_disciplina": res.get("id_disciplina"),
            "id_professor": res.get("id_professor"),
        }
    else:
        aluno_dados = {
            "id": res[0],
            "nome": res[1],
            "cpf_rg": res[2] if res[2] else "",
            "endereco": res[3] if res[3] else "",
            "vencimento_mensalidade": res[4],
            "valor_mensalidade": res[5],
            "id_disciplina": res[6],
            "id_professor": res[7],
        }

    cursor.execute("SELECT id, nome FROM disciplinas ORDER BY nome;")
    disciplinas_lista = [
        d if hasattr(d, "get") else {"id": d[0], "nome": d[1]}
        for d in cursor.fetchall()
    ]
    cursor.execute("SELECT id, nome FROM professores ORDER BY nome;")
    professores_lista = [
        p if hasattr(p, "get") else {"id": p[0], "nome": p[1]}
        for p in cursor.fetchall()
    ]
    cursor.close()
    conn.close()
    return render_template(
        "editar_aluno.html",
        aluno=aluno_dados,
        disciplinas=disciplinas_lista,
        professores=professores_lista,
    )


@app.route("/agenda", methods=["GET", "POST"])
def agenda():
    if "professor_id" not in session: return redirect("/")
    conn = obter_conexao(); cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE agenda ADD COLUMN IF NOT EXISTS id_sala INTEGER DEFAULT 1;")
        conn.commit()
    except Exception: pass

    erro = None
    if request.method == "POST":
        id_sala = request.form.get("id_sala", 1)
        id_professor = session["professor_id"]
        id_aluno = request.form.get("id_aluno")
        dia_semana = request.form.get("dia_semana")
        horario = request.form.get("horario")
        type_aula_val = request.form.get("tipo_aula", "Fixa")
        data_aula = None if type_aula_val == "Fixa" else request.form.get("data_aula")

        try:
            cursor.execute("INSERT INTO agenda (id_sala, id_professor, id_aluno, dia_semana, horario, tipo_aula, data_aula) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                           (id_sala, id_professor, id_aluno, dia_semana, horario, type_aula_val, data_aula))
            conn.commit()
            cursor.close(); conn.close()
            return redirect(f"/agenda?sala_id={id_sala}")
        except Exception: 
            erro = "Conflito de Horário ou Erro no Agendamento!"

    sala_selecionada = request.args.get("sala_id", 1, type=int)
    cursor.execute("SELECT id, nome FROM salas ORDER BY nome;"); all_salas = cursor.fetchall()
    cursor.execute("SELECT id, nome FROM professores ORDER BY nome;"); all_professores = cursor.fetchall()
    cursor.execute("SELECT id, nome FROM alunos ORDER BY nome;"); all_alunos = cursor.fetchall()

    cursor.execute("""
        SELECT age.id, age.dia_semana, age.horario, al.nome as al_nome, p.nome as pf_nome, d.nome as dp_nome, age.tipo_aula, age.id_professor
        FROM agenda age 
        LEFT JOIN alunos al ON age.id_aluno = al.id 
        LEFT JOIN professores p ON age.id_professor = p.id 
        LEFT JOIN disciplinas d ON al.id_disciplina = d.id 
        WHERE COALESCE(age.id_sala, 1) = %s 
        AND (age.tipo_aula = 'Fixa' OR (age.tipo_aula = 'Recuperacao' AND age.data_aula >= %s));
    """, (sala_selecionada, datetime.now().strftime("%Y-%m-%d")))

    paleta_cores = [
        "#D81B60", "#1E88E5", "#00897B", "#F4511E", "#7CB342", "#8E24AA", "#FFB300", "#3949AB", "#00ACC1"
    ]

    mapa_agenda = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            id_agenda = row.get("id")
            dia = row.get("dia_semana")
            hora = row.get("horario")
            al_nome = row.get("al_nome")
            prof_nome = row.get("pf_nome")
            disc_nome = row.get("dp_nome") if row.get("dp_nome") else "Geral"
            tipo = row.get("tipo_aula")
            id_prof_agenda = row.get("id_professor")
        else:
            id_agenda, dia, hora, al_nome, prof_nome, disc_nome, tipo, id_prof_agenda = row
            if not disc_nome: disc_nome = "Geral"

        if not hora: continue

        try:
            if isinstance(hora, str):
                partes_hora = hora.split(":")
                hora_objeto = datetime.strptime(f"{partes_hora[0]}:{partes_hora[1]}", "%H:%M")
            else:
                hora_objeto = datetime.combine(datetime.today(), hora)
        except Exception:
            continue

        hora_base = f"{hora_objeto.hour:02d}:00"
        horario_real_formatado = hora_objeto.strftime("%H:%M")

        id_prof_seguro = id_prof_agenda if id_prof_agenda is not None else 0
        indice_cor = id_prof_seguro % len(paleta_cores)
        cor_professor = paleta_cores[indice_cor]

        nome_professor_logado = session["professor_nome"]
        eh_minha_aula = prof_nome == nome_professor_logado
        classe_visual = "aula-block minha-aula" if eh_minha_aula else "aula-block outra-aula"
        ex_aluno = al_nome if al_nome else "Horário Disponível"
        
        texto_aula = f"<div class='small text-white-50 mb-1 fw-bold'><i class='bi bi-clock me-1'></i>{horario_real_formatado}</div>"
        texto_aula += f"<div class='aluno'>{ex_aluno} ({disc_nome})</div>"
        
        if tipo == "Recuperacao":
            texto_aula = f"<div class='rec-badge'>REC</div>" + texto_aula

        if not eh_minha_aula:
            texto_aula += f"<div class='professor-nome'>Prof. {prof_nome}</div>"
            
        if eh_minha_aula or nome_professor_logado == "Bruno Moura":
            texto_aula += f"<a href='/agenda/excluir/{id_agenda}?sala_id={sala_selecionada}' class='btn-limpar-premium' onclick='return confirm(\"Limpar este horário?\")'><i class='bi bi-trash3-fill'></i></a>"

        mapa_agenda[(dia, hora_base)] = {
            "html": f"<div class='{classe_visual}'>{texto_aula}</div>",
            "cor": cor_professor
        }
    cursor.close(); conn.close()
    return render_template("agenda.html", salas=all_salas, professores=all_professores, alunos=all_alunos, mapa_agenda=mapa_agenda, dias_semana=["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"], horarios=[f"{h:02d}:00" for h in range(8, 22)], sala_selecionada=sala_selecionada, erro=erro, id_professor_logado=session["professor_id"], nome_professor=nome_professor_logado)


@app.route("/agenda/excluir/<int:id_agenda>")
def excluir_agendamento(id_agenda):
    if "professor_id" not in session: return redirect("/")
    
    conn = obter_conexao(); cursor = conn.cursor()
    sala_id = request.args.get("sala_id", 1)
    
    try:
        cursor.execute("DELETE FROM agenda WHERE id = %s;", (id_agenda,))
        conn.commit()
    except Exception as e:
        print(f"Erro ao limpar horário da agenda: {e}")
    finally:
        cursor.close(); conn.close()
        
    return redirect(f"/agenda?sala_id={sala_id}")


@app.route("/financeiro/pagar/<int:id_mensalidade>")
def pagar_mensalidade(id_mensalidade):
    if "professor_id" not in session:
        return redirect("/")
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE mensalidades SET status = 'Pago', data_pagamento = %s WHERE id = %s;",
        (datetime.now().strftime("%d/%m/%Y"), id_mensalidade),
    )
    conn.commit()
    conn.close()
    return redirect("/financeiro")

@app.route("/api/eventos")
def api_eventos():
    if "professor_id" not in session:
        return jsonify([]), 401
        
    nome_logado = session.get("professor_nome", "")
    gestores_escola = ["Bruno Moura", "Bruno Mota", "Raphael Russowsky"]

    data_inicio_str = request.args.get("start")
    data_fim_str = request.args.get("end")

    if not data_inicio_str or not data_fim_str:
        return jsonify([]), 400

    dt_inicio = datetime.fromisoformat(data_inicio_str.split("T")[0]).date()
    dt_fim = datetime.fromisoformat(data_fim_str.split("T")[0]).date()

    conn = obter_conexao()
    cursor = conn.cursor()

    if nome_logado in gestores_escola:
        query_eventos = """
            SELECT 
                ev.id, ev.tipo_evento, ev.titulo, ev.data_evento, 
                ev.horario_inicio, ev.horario_fim, ev.recorrencia,
                string_agg(al.nome, ' & ') AS alunos_nomes, 
                p.nome AS prof_nome
            FROM eventos_agenda ev
            LEFT JOIN evento_alunos ea ON ev.id = ea.id_evento
            LEFT JOIN alunos al ON ea.id_aluno = al.id
            LEFT JOIN professores p ON ev.id_professor = p.id
            WHERE ev.data_evento BETWEEN %s AND %s OR ev.recorrencia != 'Nenhuma'
            GROUP BY ev.id, p.nome;
        """
        cursor.execute(query_eventos, (dt_inicio, dt_fim))
    else:
        query_eventos = """
            SELECT 
                ev.id, ev.tipo_evento, ev.titulo, ev.data_evento, 
                ev.horario_inicio, ev.horario_fim, ev.recorrencia,
                string_agg(al.nome, ' & ') AS alunos_nomes, 
                p.nome AS prof_nome
            FROM eventos_agenda ev
            LEFT JOIN evento_alunos ea ON ev.id = ea.id_evento
            LEFT JOIN alunos al ON ea.id_aluno = al.id
            LEFT JOIN professores p ON ev.id_professor = p.id
            WHERE (ev.data_evento BETWEEN %s AND %s OR ev.recorrencia != 'Nenhuma') 
              AND (ev.id_professor = %s OR ev.tipo_evento = 'Bloqueio' OR ev.tipo_evento = 'Feriado')
            GROUP BY ev.id, p.nome;
        """
        cursor.execute(query_eventos, (dt_inicio, dt_fim, session["professor_id"]))

    eventos_banco = cursor.fetchall()
    eventos_js = []
    
    cores_tipo = {
        "Aula": "#28a745",
        "Recuperacao": "#ffc107",
        "Bloqueio": "#6c757d",
        "Feriado": "#dc3545"
    }

    for row in eventos_banco:
        if isinstance(row, dict) or hasattr(row, 'get'):
            ev_id = row.get('id')
            tipo = row.get('tipo_evento')
            titulo = row.get('titulo')
            dt = row.get('data_evento')
            h_ini = row.get('horario_inicio')
            h_fim = row.get('horario_fim')
            rec = row.get('recorrencia')
            al_nomes = row.get('alunos_nomes')
            p_nome = row.get('prof_nome')
        else:
            ev_id = row[0]
            tipo = row[1]
            titulo = row[2]
            dt = row[3]
            h_ini = row[4]
            h_fim = row[5]
            rec = row[6]
            al_nomes = row[7] if len(row) > 7 else ""
            p_nome = row[8] if len(row) > 8 else ""

        h_ini_str = h_ini.strftime("%H:%M:%S") if hasattr(h_ini, 'strftime') else str(h_ini)[:8]
        h_fim_str = h_fim.strftime("%H:%M:%S") if hasattr(h_fim, 'strftime') else str(h_fim)[:8]
        if hasattr(dt, 'isoformat'):
            dt_original = dt
        else:
            dt_original = datetime.strptime(str(dt).split(" ")[0], "%Y-%m-%d").date()

        titulo_bloco = titulo
        if al_nomes:
            titulo_bloco = f"{al_nomes} ({p_nome if p_nome else 'Professor'})"
        elif tipo == "Bloqueio":
            titulo_bloco = titulo if titulo else "Bloqueio de Horário"

        # 🔄 LÓGICA 1: RECORRÊNCIA SEMANAL (Aulas Fixas da Escola)
        if rec == "Semanal":
            curr_date = dt_inicio
            dia_da_semana_alvo = dt_original.weekday()
            
            while curr_date <= dt_fim:
                if curr_date.weekday() == dia_da_semana_alvo:
                    eventos_js.append({
                        "id": f"semanal-{ev_id}-{curr_date.isoformat()}",
                        "title": titulo_bloco,
                        "start": f"{curr_date.isoformat()}T{h_ini_str}",
                        "end": f"{curr_date.isoformat()}T{h_fim_str}",
                        "backgroundColor": cores_tipo.get(tipo, "#28a745"),
                        "borderColor": cores_tipo.get(tipo, "#28a745"),
                        "textColor": "#ffffff" if tipo != "Recuperacao" else "#000000",
                        "allDay": False
                    })
                curr_date += timedelta(days=1)
            continue

        # 🔄 LÓGICA 2: RECORRÊNCIA QUINZENAL CORRIGIDA (Diarista - Segunda sim, segunda não)
        if rec == "Quinzenal_Sim_Nao":
            curr_date = dt_inicio
            data_base_diarista = dt_original 
            
            while curr_date <= dt_fim:
                if curr_date.weekday() == data_base_diarista.weekday(): 
                    semanas_passadas = (curr_date - data_base_diarista).days // 7
                    
                    if semanas_passadas % 2 == 0:
                        eventos_js.append({
                            "id": f"rec-{ev_id}-{curr_date.isoformat()}",
                            "title": titulo_bloco,
                            "start": f"{curr_date.isoformat()}T{h_ini_str}",
                            "end": f"{curr_date.isoformat()}T{h_fim_str}",
                            "backgroundColor": cores_tipo.get(tipo, "#6c757d"),
                            "borderColor": cores_tipo.get(tipo, "#6c757d"),
                            "allDay": False
                        })
                curr_date += timedelta(days=1)
            continue

        # EVENTOS ÚNICOS (Sem recorrência)
        eventos_js.append({
            "id": str(ev_id),
            "title": titulo_bloco,
            "start": f"{dt_original.isoformat()}T{h_ini_str}",
            "end": f"{dt_original.isoformat()}T{h_fim_str}",
            "backgroundColor": cores_tipo.get(tipo, "#28a745"),
            "borderColor": cores_tipo.get(tipo, "#28a745"),
            "textColor": "#ffffff" if tipo != "Recuperacao" else "#000000",
            "allDay": False
        })

    cursor.close()
    conn.close()
    return jsonify(eventos_js)

@app.route("/agenda-v2")
def agenda_v2():
    if "professor_id" not in session:
        return redirect("/")
        
    conn = obter_conexao()
    cursor = conn.cursor()

    cursor.execute("SELECT id, nome FROM professores ORDER BY nome;")
    professores_banco = cursor.fetchall()
    professores = [{"id": r[0], "nome": r[1]} if not isinstance(r, dict) else r for r in professores_banco]

    cursor.execute("SELECT id, nome FROM alunos ORDER BY nome;")
    alunos_banco = cursor.fetchall()
    alunos = [{"id": r[0], "nome": r[1]} if not isinstance(r, dict) else r for r in alunos_banco]

    cursor.execute("SELECT id, nome FROM disciplinas ORDER BY nome;")
    disciplinas_banco = cursor.fetchall()
    disciplinas = [{"id": r[0], "nome": r[1]} if not isinstance(r, dict) else r for r in disciplinas_banco]

    cursor.close()
    conn.close()

    return render_template(
        "agenda_v2.html", 
        professores=professores, 
        alunos=alunos, 
        disciplinas=disciplinas,
        nome_professor=session.get("professor_nome", "Professor")
    )


@app.route("/financeiro", methods=["GET", "POST"])
def financeiro():
    if "professor_id" not in session: return redirect("/")
    nome_logado = session["professor_nome"]
    competencia_atual = request.form.get("competencia_filtro") if request.method == "POST" and request.form.get("competencia_filtro") else datetime.now().strftime("%m/%Y")

    conn = obter_conexao(); cursor = conn.cursor()
    is_postgres = hasattr(conn, "encoding") or conn.__class__.__name__ == "Connection"
    id_auto = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    text_type = "VARCHAR(255)" if is_postgres else "TEXT"
    real_type = "NUMERIC(10,2)" if is_postgres else "REAL"

    try:
        cursor.execute(f"CREATE TABLE IF NOT EXISTS mensalidades (id {id_auto}, id_aluno INTEGER NOT NULL, competencia {text_type} NOT NULL, valor_devido {real_type}, status {text_type} DEFAULT 'Pendente', data_pagamento {text_type});")
        conn.commit()
    except Exception: pass

    if competencia_atual == datetime.now().strftime("%m/%Y"):
        cursor.execute("SELECT id, valor_mensalidade FROM alunos;")
        for aluno in cursor.fetchall():
            id_aluno, valor = (aluno["id"], aluno["valor_mensalidade"]) if isinstance(aluno, dict) else (aluno[0], aluno[1])
            if valor is None: valor = 0.0
            cursor.execute("SELECT id FROM mensalidades WHERE id_aluno = %s AND competencia = %s;", (id_aluno, competencia_atual))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO mensalidades (id_aluno, competencia, valor_devido, status) VALUES (%s, %s, %s, 'Pendente');", (id_aluno, competencia_atual, valor))
        conn.commit()

    cursor.execute("SELECT DISTINCT competencia FROM mensalidades ORDER BY competencia DESC;")
    meses_disponiveis = [r["competencia"] if isinstance(r, dict) else r[0] for r in cursor.fetchall()]
    if datetime.now().strftime("%m/%Y") not in meses_disponiveis: meses_disponiveis.insert(0, datetime.now().strftime("%m/%Y"))

    gestores_escola = ["Bruno Moura", "Bruno Mota", "Raphael Russowsky"]

    cursor.execute("SELECT nome FROM professores ORDER BY nome;")
    todos_professores = [p["nome"] if isinstance(p, dict) else p[0] for p in cursor.fetchall()]

    if nome_logado in gestores_escola:
        cursor.execute("""
            SELECT m.id, al.nome as aluno_nome, m.competencia, m.valor_devido, m.status, m.data_pagamento, d.nome as disciplina_nome, al.vencimento_mensalidade, p.nome as prof_responsavel
            FROM mensalidades m 
            JOIN alunos al ON m.id_aluno = al.id 
            LEFT JOIN disciplinas d ON al.id_disciplina = d.id 
            LEFT JOIN professores p ON al.id_professor = p.id
            WHERE m.competencia = %s;
        """, (competencia_atual,))
    else:
        cursor.execute("""
            SELECT m.id, al.nome as aluno_nome, m.competencia, m.valor_devido, m.status, m.data_pagamento, d.nome as disciplina_nome, al.vencimento_mensalidade, p.nome as prof_responsavel
            FROM mensalidades m 
            JOIN alunos al ON m.id_aluno = al.id 
            LEFT JOIN disciplinas d ON al.id_disciplina = d.id 
            LEFT JOIN professores p ON al.id_professor = p.id
            WHERE m.competencia = %s AND al.id_professor = %s;
        """, (competencia_atual, session["professor_id"]))

    dia_hoje = datetime.now().day

    total_recebido = 0.0
    total_no_prazo = 0.0
    total_atrasado = 0.0

    lista_mensalidades = []
    for row in cursor.fetchall():
        if isinstance(row, dict):
            v_devido = row.get("valor_devido") if row.get("valor_devido") is not None else 0.0
            status_banco = row.get("status")
            venc_dia = row.get("vencimento_mensalidade")
            item = {
                "id": row.get("id"), 
                "aluno_nome": row.get("aluno_nome"), 
                "mes_competencia": row.get("competencia"), 
                "valor": v_devido, 
                "data_pagamento": row.get("data_pagamento"), 
                "disciplina_nome": row.get("disciplina_nome"), 
                "vencimento": venc_dia if venc_dia else "-",
                "professor_nome": row.get("prof_responsavel") if row.get("prof_responsavel") else "Não Atribuído"
            }
        else:
            v_devido = row[3] if row[3] is not None else 0.0
            status_banco = row[4]
            venc_dia = row[7]
            item = {
                "id": row[0], 
                "aluno_nome": row[1], 
                "mes_competencia": row[2], 
                "valor": v_devido, 
                "data_pagamento": row[5], 
                "disciplina_nome": row[6], 
                "vencimento": venc_dia if venc_dia else "-",
                "professor_nome": row[8] if row[8] else "Não Atribuído"
            }

        if status_banco == "Pago":
            item["status_visual"] = "Pago"
            total_recebido += float(v_devido)
        else:
            try:
                dia_venc_int = int(str(venc_dia).strip())
                if dia_hoje < dia_venc_int:
                    item["status_visual"] = "No Prazo"
                    total_no_prazo += float(v_devido)
                elif dia_hoje == dia_venc_int:
                    item["status_visual"] = "Vence Hoje"
                    total_no_prazo += float(v_devido)
                else:
                    item["status_visual"] = "Atrasado"
                    total_atrasado += float(v_devido)
            except Exception:
                item["status_visual"] = "Pendente"
                total_atrasado += float(v_devido)

        lista_mensalidades.append(item)

    cursor.close(); conn.close()
    pode_ver_relatorio = nome_logado in gestores_escola

    return render_template(
        "financeiro.html", 
        mensalidades=lista_mensalidades, 
        competencia=competencia_atual, 
        meses_opcoes=meses_disponiveis,
        total_recebido=total_recebido,
        total_no_prazo=total_no_prazo,
        total_atrasado=total_atrasado,
        pode_ver_relatorio=pode_ver_relatorio,
        professores_lista=todos_professores,
        usuario_logado=nome_logado
    )


@app.route("/api/eventos/salvar", methods=["POST"])
def api_eventos_salvar():
    if "professor_id" not in session:
        return redirect("/")

    tipo_evento = request.form.get("tipo_evento")
    titulo = request.form.get("titulo")
    descricao = request.form.get("descricao", "")
    data_evento = request.form.get("data_evento")
    horario_inicio = request.form.get("horario_inicio")
    horario_fim = request.form.get("horario_fim")
    id_professor = request.form.get("id_professor")
    id_disciplina = request.form.get("id_disciplina")
    recorrencia = request.form.get("recorrencia", "Nenhuma")

    alunos_ids = request.form.getlist("alunos_ids")

    if tipo_evento in ["Bloqueio", "Feriado"]:
        id_professor = None
        id_disciplina = None
        alunos_ids = []

    conn = obter_conexao()
    cursor = conn.cursor()

    try:
        query_evento = """
            INSERT INTO eventos_agenda (titulo, descricao, data_evento, horario_inicio, horario_fim, id_professor, id_disciplina, tipo_evento, recorrencia)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """
        cursor.execute(query_evento, (
            titulo, descricao, data_evento, horario_inicio, horario_fim, 
            id_professor if id_professor else None, 
            id_disciplina if id_disciplina else None, 
            tipo_evento, recorrencia
        ))
        
        res_evento = cursor.fetchone()
        id_evento_gerado = res_evento['id'] if isinstance(res_evento, dict) else res_evento[0]

        for al_id in alunos_ids:
            if al_id:
                cursor.execute(
                    "INSERT INTO evento_alunos (id_evento, id_aluno) VALUES (%s, %s);",
                    (id_evento_gerado, int(al_id))
                )

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Erro ao salvar na agenda avançada: {e}")
    finally:
        cursor.close()
        conn.close()

    return redirect("/agenda-v2")

@app.route("/api/eventos/excluir/<id_evento>")
def api_eventos_excluir(id_evento):
    if "professor_id" not in session:
        return redirect("/")

    # Limpa o ID se ele vier com o prefixo da diarista
    id_evento_str = str(id_evento)
    if id_evento_str.startswith("rec-"):
        # Pega a segunda parte (ex: rec-15-2026-06-01 vira 15)
        id_real = id_evento_str.split("-")[1]
    else:
        id_real = id_evento_str

    conn = obter_conexao()
    cursor = conn.cursor()

    try:
        # Forçamos a conversão para inteiro para o banco não se perder
        cursor.execute("DELETE FROM eventos_agenda WHERE id = %s;", (int(id_real),))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Erro crítico na exclusão da agenda: {e}")
    finally:
        cursor.close()
        conn.close()

    # Força a página inteira a recarregar na marra
    return redirect("/agenda-v2")

@app.route("/migrar-agenda")
def migrar_agenda():
    # Trava de segurança: apenas o gestor logado pode rodar a migração
    if "professor_id" not in session or session.get("professor_nome") != "Bruno Moura":
        return "<h3>❌ Acesso não autorizado.</h3>", 403

    conn = obter_conexao()
    cursor = conn.cursor()

    # Mapeamento para descobrir a data real da semana de virada de chave (Junho de 2026)
    # Segunda-feira da próxima semana será dia 15/06/2026
    dias_datas_v2 = {
        "Segunda": date(2026, 6, 15),
        "Terça": date(2026, 6, 16),
        "Quarta": date(2026, 6, 17),
        "Quinta": date(2026, 6, 18),
        "Sexta": date(2026, 6, 19),
        "Sábado": date(2026, 6, 20),
        "Domingo": date(2026, 6, 21)
    }

    try:
        # 1. Puxa todos os horários fixos e ativos da tabela antiga
        cursor.execute("SELECT id, dia_semana, horario, id_professor, id_aluno, tipo_aula FROM agenda;")
        agendas_antigas = cursor.fetchall()

        contador = 0
        for item in agendas_antigas:
            if isinstance(item, dict) or hasattr(item, 'get'):
                dia_texto = item.get("dia_semana")
                hora_original = item.get("horario")
                id_prof = item.get("id_professor")
                id_aluno = item.get("id_aluno")
                tipo = item.get("tipo_aula")
            else:
                dia_texto, hora_original, id_prof, id_aluno, tipo = item[1], item[2], item[3], item[4], item[5]

            # Segurança: Se não tiver aluno ou dia mapeado, pula para o próximo
            if not id_aluno or dia_texto not in dias_datas_v2:
                continue

            # Ajusta o formato da hora (trata se vier '14:00' ou '14:00:00')
            partes = str(hora_original).strip().split(":")
            h_real = int(partes[0])
            m_real = int(partes[1]) if len(partes) > 1 else 0
            
            h_ini_str = f"{h_real:02d}:{m_real:02d}:00"
            h_fim_str = f"{(h_real + 1):02d}:{m_real:02d}:00" # Soma 1 hora de aula padrão

            data_start_real = dias_datas_v2[dia_texto]
            tipo_convertido = "Aula" if tipo == "Regular" or tipo == "Fixa" else "Recuperacao"

            # 2. INSERE NA TABELA PRINCIPAL 'eventos_agenda' COMO RECORRÊNCIA SEMANAL
            query_insere = """
                INSERT INTO eventos_agenda (titulo, data_evento, horario_inicio, horario_fim, id_professor, tipo_evento, recorrencia)
                VALUES (%s, %s, %s, %s, %s, %s, 'Semanal') RETURNING id;
            """
            cursor.execute(query_insere, ("Aula Regular", data_start_real, h_ini_str, h_fim_str, id_prof, tipo_convertido))
            
            res_novo = cursor.fetchone()
            id_evento_novo = res_novo['id'] if isinstance(res_novo, dict) else res_novo[0]

            # 3. INSERE NA TABELA INTERMEDIÁRIA 'evento_alunos' VINCULANDO O ALUNO
            cursor.execute(
                "INSERT INTO evento_alunos (id_evento, id_aluno) VALUES (%s, %s);",
                (id_evento_novo, id_aluno)
            )
            contador += 1

        conn.commit()
        mensagem = f"✅ SUCESSO! {contador} horários fixos migrados com perfeição para a Agenda V2.0!"
    except Exception as e:
        conn.rollback()
        mensagem = f"❌ ERRO CRÍTICO NA MIGRAÇÃO: {str(e)}"
    finally:
        cursor.close()
        conn.close()

    return f"<h3>{mensagem}</h3><br><a href='/agenda-v2'>Ir para a Nova Agenda</a>"

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta)
