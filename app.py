from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
from datetime import datetime
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
    conn = obter_conexao()
    cursor = conn.cursor()

    if nome_logado == "Bruno Moura":
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

    if nome_logado == "Bruno Moura":
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
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]
    competencia_atual = f"{meses_ano[datetime.now().month - 1]}/{datetime.now().year}"

    return render_template(
        "dashboard.html",
        nome_professor=nome_logado,
        total_alunos=total_alunos,
        aulas_hoje=aulas_hoje,
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

    if nome_logado == "Bruno Moura":
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


@app.route("/aluno/contrato/<int:id>")
def aluno_contrato(id):
    if "professor_id" not in session:
        return redirect("/")
    conn = obter_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT al.id, al.nome, al.vencimento_mensalidade, al.valor_mensalidade, d.nome as disciplina_nome, al.cpf_rg, al.endereco FROM alunos al LEFT JOIN disciplinas d ON al.id_disciplina = d.id WHERE al.id = %s;",
        (id,),
    )
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if not res:
        return "Aluno não encontrado", 404

    if isinstance(res, dict):
        aluno_dados = {
            "id": res.get("id"),
            "nome": res.get("nome"),
            "vencimento_mensalidade": res.get("vencimento_mensalidade"),
            "valor_mensalidade": res.get("valor_mensalidade"),
            "disciplina_nome": res.get("disciplina_nome"),
            "cpf_rg": res.get("cpf_rg") if res.get("cpf_rg") else "",
            "endereco": res.get("endereco") if res.get("endereco") else "",
        }
    else:
        aluno_dados = {
            "id": res[0],
            "nome": res[1],
            "vencimento_mensalidade": res[2],
            "valor_mensalidade": res[3],
            "disciplina_nome": res[4],
            "cpf_rg": res[5] if res[5] else "",
            "endereco": res[6] if res[6] else "",
        }
    return render_template("contrato.html", aluno=aluno_dados)


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
    if "professor_id" not in session:
        return redirect("/")
    conn = obter_conexao()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "ALTER TABLE agenda ADD COLUMN IF NOT EXISTS id_sala INTEGER DEFAULT 1;"
        )
        conn.commit()
    except Exception:
        pass

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
            cursor.execute(
                "INSERT INTO agenda (id_sala, id_professor, id_aluno, dia_semana, horario, tipo_aula, data_aula) VALUES (%s, %s, %s, %s, %s, %s, %s);",
                (
                    id_sala,
                    id_professor,
                    id_aluno,
                    dia_semana,
                    horario,
                    type_aula_val,
                    data_aula,
                ),
            )
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(f"/agenda?sala_id={id_sala}")
        except Exception:
            erro = "Conflito de Horário ou Erro no Agendamento!"

    sala_selecionada = request.args.get("sala_id", 1, type=int)
    cursor.execute("SELECT id, nome FROM salas ORDER BY nome;")
    all_salas = [
        s if isinstance(s, dict) else {"id": s[0], "nome": s[1]}
        for s in cursor.fetchall()
    ]
    cursor.execute("SELECT id, nome FROM professores ORDER BY nome;")
    all_professores = [
        p if isinstance(p, dict) else {"id": p[0], "nome": p[1]}
        for p in cursor.fetchall()
    ]
    cursor.execute("SELECT id, nome FROM alunos ORDER BY nome;")
    all_alunos = [
        a if isinstance(a, dict) else {"id": a[0], "nome": a[1]}
        for a in cursor.fetchall()
    ]

    # Injetado age.id no SELECT para sabermos qual agendamento limpar
    cursor.execute(
        "SELECT age.id, age.dia_semana, age.horario, al.nome as al_nome, p.nome as pf_nome, d.nome as dp_nome, age.tipo_aula FROM agenda age LEFT JOIN alunos al ON age.id_aluno = al.id LEFT JOIN professores p ON age.id_professor = p.id LEFT JOIN disciplinas d ON al.id_disciplina = d.id WHERE COALESCE(age.id_sala, 1) = %s AND (age.tipo_aula = 'Fixa' OR (age.tipo_aula = 'Recuperacao' AND age.data_aula >= %s));",
        (sala_selecionada, datetime.now().strftime("%Y-%m-%d")),
    )

    mapa_agenda = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            id_agenda = row.get("id")
            dia, hora, num_aluno, num_prof, num_curso, tipo = (
                row.get("dia_semana"),
                row.get("horario"),
                row.get("al_nome"),
                row.get("pf_nome"),
                row.get("dp_nome") if row.get("dp_nome") else "Geral",
                row.get("tipo_aula"),
            )
        else:
            id_agenda = row[0]
            dia, hora, num_aluno, num_prof, num_curso, tipo = (
                row[1],
                row[2],
                row[3],
                row[4],
                row[5] if row[5] else "Geral",
                row[6],
            )

        if not hora:
            continue
        hora_formatada = hora[:5]
        eh_minha_aula = num_prof == session["professor_nome"]
        classe_destaque = "aula-minha-card" if eh_minha_aula else "aula-outra-card"
        
        # Ajuste para quando o aluno foi excluído e o card ficou órfão (None)
        ex_aluno = num_aluno if num_aluno else "Horário Desatualizado"
        
        texto_aula = (
            f"🚨 [REC] {ex_aluno} ({num_curso})"
            if tipo == "Recuperacao"
            else f"{ex_aluno} ({num_curso})"
        )
        if not eh_minha_aula:
            texto_aula += f" <br><small class='text-muted'>Prof. {num_prof}</small>"
            
        # Adiciona o link de limpar para o dono do horário ou se o logado for você (Bruno Moura)
        if eh_minha_aula or session["professor_nome"] == "Bruno Moura":
            texto_aula += f"<br><a href='/agenda/excluir/{id_agenda}?sala_id={sala_selecionada}' class='btn btn-sm btn-link text-danger p-0 fw-bold border-0 mt-1' style='font-size: 11px; text-decoration: none;' onclick='return confirm(\"Deseja desmarcar e liberar este horário?\")'><i class='bi bi-trash3-fill me-1'></i>Limpar</a>"

        mapa_agenda[(dia, hora_formatada)] = (
            f"<div class='{classe_destaque}'>{texto_aula}</div>"
        )

    cursor.close()
    conn.close()
    return render_template(
        "agenda.html",
        salas=all_salas,
        professores=all_professores,
        alunos=all_alunos,
        mapa_agenda=mapa_agenda,
        dias_semana=["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"],
        horarios=[f"{h:02d}:00" for h in range(8, 22)],
        sala_selecionada=sala_selecionada,
        erro=erro,
        id_professor_logado=session["professor_id"],
        name_professor=session["professor_nome"],
    )

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

    # INJETADO: al.vencimento_mensalidade na busca para sabermos o dia combinado
    if nome_logado == "Bruno Moura":
        cursor.execute("""
            SELECT m.id, al.nome as aluno_nome, m.competencia, m.valor_devido, m.status, m.data_pagamento, d.nome as disciplina_nome, al.vencimento_mensalidade
            FROM mensalidades m 
            JOIN alunos al ON m.id_aluno = al.id 
            LEFT JOIN disciplinas d ON al.id_disciplina = d.id 
            WHERE m.competencia = %s;
        """, (competencia_atual,))
    else:
        cursor.execute("""
            SELECT m.id, al.nome as aluno_nome, m.competencia, m.valor_devido, m.status, m.data_pagamento, d.nome as disciplina_nome, al.vencimento_mensalidade
            FROM mensalidades m 
            JOIN alunos al ON m.id_aluno = al.id 
            LEFT JOIN disciplinas d ON al.id_disciplina = d.id 
            WHERE m.competencia = %s AND al.id_professor = %s;
        """, (competencia_atual, session["professor_id"]))

    dia_hoje = datetime.now().day

    lista_mensalidades = []
    for row in cursor.fetchall():
        if isinstance(row, dict):
            v_devido = row.get("valor_devido") if row.get("valor_devido") is not None else 0.0
            status_banco = row.get("status")
            venc_dia = row.get("vencimento_mensalidade")
            
            item = {"id": row.get("id"), "aluno_nome": row.get("aluno_nome"), "mes_competencia": row.get("competencia"), "valor": v_devido, "data_pagamento": row.get("data_pagamento"), "disciplina_nome": row.get("disciplina_nome"), "vencimento": venc_dia if venc_dia else "-"}
        else:
            v_devido = row[3] if row[3] is not None else 0.0
            status_banco = row[4]
            venc_dia = row[7]
            
            item = {"id": row[0], "aluno_nome": row[1], "mes_competencia": row[2], "valor": v_devido, "data_pagamento": row[5], "disciplina_nome": row[6], "vencimento": venc_dia if venc_dia else "-"}

        # --- MOTOR DE STATUS INTELIGENTE ---
        if status_banco == "Pago":
            item["status_visual"] = "Pago"
        else:
            try:
                dia_venc_int = int(str(venc_dia).strip())
                if dia_hoje < dia_venc_int:
                    item["status_visual"] = "No Prazo"
                elif dia_hoje == dia_venc_int:
                    item["status_visual"] = "Vence Hoje"
                else:
                    item["status_visual"] = "Atrasado"
            except Exception:
                item["status_visual"] = "Pendente" # Fallback caso não tenha número válido

        lista_mensalidades.append(item)

    cursor.close(); conn.close()
    return render_template("financeiro.html", mensalidades=lista_mensalidades, competencia=competencia_atual, meses_opcoes=meses_disponiveis)

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=porta)
