import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
from datetime import datetime
from scipy.stats import norm
import socket

app = Flask(__name__, static_folder="static", template_folder="templates")

DB_FILE = "brasileirao.db"

# -----------------------------
# Lista de times e dados iniciais (mantive igual ao seu Gradio)
# -----------------------------
times_list = [
    "Atlético-MG", "Bahia", "Botafogo", "Ceará", "Corinthians",
    "Cruzeiro", "Flamengo", "Fluminense", "Fortaleza", "Juventude",
    "Grêmio", "Internacional", "Mirassol", "Palmeiras", "RB Bragantino",
    "Santos", "São Paulo", "Sport", "Vasco", "Vitória"
]

dados_iniciais = [
    ["Palmeiras",29,19,5,5,"53:26",62],
    ["Flamengo",29,18,7,4,"56:16",61],
    ["Cruzeiro",30,16,9,5,"42:21",57],
    ["Mirassol",30,15,10,5,"52:31",55],
    ["Bahia",30,14,7,9,"40:34",49],
    ["Botafogo",30,13,8,9,"41:28",47],
    ["Fluminense",29,13,5,11,"36:35",44],
    ["Vasco",30,12,6,12,"49:41",42],
    ["São Paulo",30,11,8,11,"33:33",41],
    ["Corinthians",30,10,9,11,"32:35",39],
    ["Grêmio",30,10,9,11,"33:38",39],
    ["RB Bragantino",30,10,6,14,"34:47",36],
    ["Atlético-MG",29,9,9,11,"27:32",36],
    ["Ceará",29,9,8,12,"27:28",35],
    ["Internacional",30,9,8,13,"35:43",35],
    ["Santos",29,8,8,13,"30:42",32],
    ["Vitória",30,7,10,13,"27:44",31],
    ["Fortaleza",29,7,6,16,"27:44",27],
    ["Juventude",30,7,5,18,"24:56",26],
    ["Sport",29,2,11,16,"22:46",17]
]

# -----------------------------
# DB helpers
# -----------------------------
def get_conn():
    return sqlite3.connect(DB_FILE, timeout=30)

def criar_tabelas_e_base():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS tabela_base (
        Time TEXT PRIMARY KEY,
        Jogos INTEGER, V INTEGER, E INTEGER, D INTEGER,
        GM INTEGER, GS INTEGER, Pontos INTEGER
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS tabela (
        Time TEXT PRIMARY KEY,
        Jogos INTEGER, V INTEGER, E INTEGER, D INTEGER,
        GM INTEGER, GS INTEGER, Pontos INTEGER
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Data TEXT,
        Time1 TEXT,
        Time2 TEXT,
        Gols1 INTEGER,
        Gols2 INTEGER
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS jogos_futuros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Data TEXT,
        Time1 TEXT,
        Time2 TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS cartoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Time TEXT,
        Jogador TEXT,
        Amarelo INTEGER,
        Vermelho INTEGER
    )
    """)
    conn.commit()

    # popular tabela_base se vazia
    c.execute("SELECT COUNT(*) FROM tabela_base")
    if c.fetchone()[0] == 0:
        for row in dados_iniciais:
            gm, gs = map(int, row[5].split(":"))
            c.execute("INSERT INTO tabela_base(Time,Jogos,V,E,D,GM,GS,Pontos) VALUES(?,?,?,?,?,?,?,?)",
                      (row[0], row[1], row[2], row[3], row[4], gm, gs, row[6]))
        conn.commit()

    # inicializa tabela atual
    c.execute("SELECT COUNT(*) FROM tabela")
    if c.fetchone()[0] == 0:
        c.execute("DELETE FROM tabela")
        c.execute("INSERT INTO tabela SELECT * FROM tabela_base")
        conn.commit()
    conn.close()

criar_tabelas_e_base()

# -----------------------------
# Reconstruir tabela atual (mesma lógica)
# -----------------------------
def reconstruir_tabela():
    conn = get_conn()
    df_base = pd.read_sql("SELECT * FROM tabela_base", conn, index_col="Time")
    df_base[['Jogos','V','E','D','GM','GS','Pontos']] = df_base[['Jogos','V','E','D','GM','GS','Pontos']].astype(int)
    df = df_base.copy()
    df_matches = pd.read_sql("SELECT * FROM matches ORDER BY id ASC", conn)
    for _, m in df_matches.iterrows():
        t1, t2, g1, g2 = m['Time1'], m['Time2'], int(m['Gols1']), int(m['Gols2'])
        df.at[t1, 'Jogos'] += 1; df.at[t2, 'Jogos'] += 1
        df.at[t1, 'GM'] += g1; df.at[t1, 'GS'] += g2
        df.at[t2, 'GM'] += g2; df.at[t2, 'GS'] += g1
        if g1 > g2:
            df.at[t1, 'V'] += 1; df.at[t2, 'D'] += 1; df.at[t1, 'Pontos'] += 3
        elif g1 < g2:
            df.at[t2, 'V'] += 1; df.at[t1, 'D'] += 1; df.at[t2, 'Pontos'] += 3
        else:
            df.at[t1, 'E'] += 1; df.at[t2, 'E'] += 1; df.at[t1, 'Pontos'] += 1; df.at[t2, 'Pontos'] += 1
    df_to_store = df.reset_index()
    df_to_store.to_sql("tabela", conn, if_exists="replace", index=False)
    conn.close()
    df_display = df_to_store.sort_values(by=['Pontos','V'], ascending=[False, False]).reset_index(drop=True)
    df_display.index += 1
    return df_display

# -----------------------------
# Funções de gerenciamento (mesmas que você tinha)
# -----------------------------
def adicionar_resultado(data_str, time1, time2, gols1, gols2):
    conn = get_conn(); c = conn.cursor()
    try:
        data_use = datetime.strptime(data_str, "%d/%m/%Y").strftime("%d/%m/%Y")
    except:
        data_use = data_str
    c.execute("INSERT INTO matches (Data,Time1,Time2,Gols1,Gols2) VALUES (?,?,?,?,?)",
              (data_use, time1, time2, int(gols1), int(gols2)))
    conn.commit(); conn.close()
    df = reconstruir_tabela()
    matches_df = pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn())
    return df, matches_df

def atualizar_resultado(match_id, data_str, time1, time2, gols1, gols2):
    conn = get_conn(); c = conn.cursor()
    try:
        data_use = datetime.strptime(data_str, "%d/%m/%Y").strftime("%d/%m/%Y")
    except:
        data_use = data_str
    c.execute("UPDATE matches SET Data=?,Time1=?,Time2=?,Gols1=?,Gols2=? WHERE id=?",
              (data_use, time1, time2, int(gols1), int(gols2), int(match_id)))
    conn.commit(); conn.close()
    df = reconstruir_tabela()
    matches_df = pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn())
    return df, matches_df

def excluir_resultado(match_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM matches WHERE id=?", (int(match_id),))
    conn.commit(); conn.close()
    df = reconstruir_tabela()
    matches_df = pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn())
    return df, matches_df

# -----------------------------
# Jogos futuros / probabilidades
# -----------------------------
def adicionar_jogo_futuro_db(data_str, time1, time2):
    conn = get_conn(); c = conn.cursor()
    try:
        data_use = datetime.strptime(data_str, "%d/%m/%Y").strftime("%d/%m/%Y")
    except:
        data_use = data_str
    c.execute("INSERT INTO jogos_futuros (Data,Time1,Time2) VALUES (?,?,?)", (data_use,time1,time2))
    conn.commit(); conn.close()
    df = pd.read_sql("SELECT * FROM jogos_futuros ORDER BY id DESC", get_conn())
    return df

def analisar_jogos_futuros_db(time):
    conn = get_conn()
    df_fut = pd.read_sql("SELECT * FROM jogos_futuros ORDER BY Data ASC", conn)
    conn.close()
    jogos_time = df_fut[(df_fut['Time1']==time) | (df_fut['Time2']==time)]
    resumo = f"{len(jogos_time)} jogo(s) futuro(s) para {time}."
    return jogos_time, resumo

def calcular_probabilidades(time):
    conn = get_conn()
    df_tab = pd.read_sql("SELECT * FROM tabela", conn, index_col="Time")
    df_fut = pd.read_sql("SELECT * FROM jogos_futuros", conn)
    conn.close()
    pontos_atual = df_tab.at[time, 'Pontos']
    jogos_restantes = df_fut[(df_fut['Time1']==time) | (df_fut['Time2']==time)].shape[0]
    p_win, p_draw, p_loss = 0.35, 0.30, 0.35
    mu = pontos_atual + jogos_restantes * (3*p_win + 1*p_draw)
    sigma = (jogos_restantes * ((3-1)**2*p_win + (1-1)**2*p_draw + (0-1)**2*p_loss))**0.5
    prob_rebaix = norm.cdf(42, loc=mu, scale=sigma)
    prob_libertadores = 1 - norm.cdf(60, loc=mu, scale=sigma)
    prob_nada = max(0, 1 - prob_rebaix - prob_libertadores)
    return pd.DataFrame({
        "Cenário": ["Rebaixamento", "Libertadores", "Nenhum objetivo"],
        "Probabilidade": [f"{prob_rebaix*100:.1f}%", f"{prob_libertadores*100:.1f}%", f"{prob_nada*100:.1f}%"]
    })

def analisar_jogos_futuros_com_prob(time):
    jogos_df, resumo = analisar_jogos_futuros_db(time)
    prob_df = calcular_probabilidades(time)
    return jogos_df, resumo, prob_df

# -----------------------------
# Cartões
# -----------------------------
def registrar_cartao_db(time, jogador, amarelo, vermelho):
    conn = get_conn(); c = conn.cursor()
    amarelo, vermelho = int(amarelo), int(vermelho)
    c.execute("SELECT id,Amarelo,Vermelho FROM cartoes WHERE Time=? AND Jogador=?", (time,jogador))
    row = c.fetchone()
    if row:
        id_, a, v = row
        a += amarelo; v += vermelho
        c.execute("UPDATE cartoes SET Amarelo=?,Vermelho=? WHERE id=?", (a,v,id_))
    else:
        c.execute("INSERT INTO cartoes (Time,Jogador,Amarelo,Vermelho) VALUES (?,?,?,?)", (time,jogador,amarelo,vermelho))
    conn.commit(); conn.close()
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM cartoes ORDER BY id DESC", conn); conn.close()
    aviso = ""
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT Amarelo,Vermelho FROM cartoes WHERE Time=? AND Jogador=?", (time,jogador))
    r = c.fetchone(); conn.close()
    if r and (r[0] >= 3 or r[1] >= 1):
        aviso = f"Atenção! Jogador {jogador} do {time} está suspenso ou perto da suspensão."
    return df, aviso

# -----------------------------
# Rotas principais e APIs (retornam snippets HTML para atualizar abas)
# -----------------------------
@app.route('/')
def index():
    # renderiza a página com as tabs e lista de times
    return render_template('index.html', times_list=times_list)

@app.route('/api/classificacao')
def api_classificacao():
    df = reconstruir_tabela()
    # converte para HTML (usando classes bootstrap)
    html = df.to_html(classes="table table-striped table-sm", index=True)
    return html

@app.route('/api/matches')
def api_matches():
    df = pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn())
    html = df.to_html(classes="table table-striped table-sm", index=False)
    return html

@app.route('/api/jogos_futuros')
def api_jogos_futuros():
    df = pd.read_sql("SELECT * FROM jogos_futuros ORDER BY id DESC", get_conn())
    html = df.to_html(classes="table table-striped table-sm", index=False)
    return html

@app.route('/api/cartoes')
def api_cartoes():
    df = pd.read_sql("SELECT * FROM cartoes ORDER BY id DESC", get_conn())
    html = df.to_html(classes="table table-striped table-sm", index=False)
    return html

# ---------- ações: adicionar / atualizar / excluir ----------
@app.route('/action/add_result', methods=['POST'])
def action_add_result():
    data = request.form.get('data') or ""
    t1 = request.form.get('time1') or ""
    t2 = request.form.get('time2') or ""
    g1 = request.form.get('g1') or 0
    g2 = request.form.get('g2') or 0
    if t1 == t2:
        return jsonify({"success": False, "msg": "Mandante e visitante iguais."})
    df, matches = adicionar_resultado(data, t1, t2, g1, g2)
    # retornamos HTML atualizado para as duas abas relevantes
    return jsonify({
        "success": True,
        "msg": "Resultado adicionado.",
        "classificacao_html": reconstruir_tabela().to_html(classes="table table-striped table-sm", index=True),
        "matches_html": pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn()).to_html(classes="table table-striped table-sm", index=False)
    })

@app.route('/action/update_result', methods=['POST'])
def action_update_result():
    mid = request.form.get('id')
    data = request.form.get('data') or ""
    t1 = request.form.get('time1') or ""
    t2 = request.form.get('time2') or ""
    g1 = request.form.get('g1') or 0
    g2 = request.form.get('g2') or 0
    if not mid:
        return jsonify({"success": False, "msg": "ID inválido."})
    if t1 == t2:
        return jsonify({"success": False, "msg": "Mandante e visitante iguais."})
    df, matches = atualizar_resultado(int(mid), data, t1, t2, g1, g2)
    return jsonify({
        "success": True,
        "msg": "Resultado atualizado.",
        "classificacao_html": reconstruir_tabela().to_html(classes="table table-striped table-sm", index=True),
        "matches_html": pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn()).to_html(classes="table table-striped table-sm", index=False)
    })

@app.route('/action/delete_result', methods=['POST'])
def action_delete_result():
    mid = request.form.get('id')
    if not mid:
        return jsonify({"success": False, "msg": "ID inválido."})
    df, matches = excluir_resultado(int(mid))
    return jsonify({
        "success": True,
        "msg": "Resultado excluído.",
        "classificacao_html": reconstruir_tabela().to_html(classes="table table-striped table-sm", index=True),
        "matches_html": pd.read_sql("SELECT * FROM matches ORDER BY id DESC", get_conn()).to_html(classes="table table-striped table-sm", index=False)
    })

@app.route('/action/add_futuro', methods=['POST'])
def action_add_futuro():
    data = request.form.get('data') or ""
    t1 = request.form.get('time1') or ""
    t2 = request.form.get('time2') or ""
    df = adicionar_jogo_futuro_db(data, t1, t2)
    return jsonify({
        "success": True,
        "msg": "Jogo futuro adicionado.",
        "futuros_html": pd.read_sql("SELECT * FROM jogos_futuros ORDER BY id DESC", get_conn()).to_html(classes="table table-striped table-sm", index=False)
    })

@app.route('/action/get_fut_analysis', methods=['GET'])
def action_get_fut_analysis():
    time = request.args.get('time')
    if not time:
        return jsonify({"success": False, "msg": "Time não informado."})
    jogos_df, resumo, prob_df = analisar_jogos_futuros_com_prob(time)
    return jsonify({
        "success": True,
        "resumo": resumo,
        "jogos_html": jogos_df.to_html(classes="table table-striped table-sm", index=False),
        "prob_html": prob_df.to_html(classes="table table-striped table-sm", index=False)
    })

@app.route('/action/add_cartao', methods=['POST'])
def action_add_cartao():
    time = request.form.get('time') or ""
    jogador = request.form.get('jogador') or ""
    amarelo = request.form.get('amarelo') or 0
    vermelho = request.form.get('vermelho') or 0
    df, aviso = registrar_cartao_db(time, jogador, amarelo, vermelho)
    return jsonify({
        "success": True,
        "msg": "Cartão registrado.",
        "cartoes_html": df.to_html(classes="table table-striped table-sm", index=False),
        "aviso": aviso
    })

# -----------------------------
# Executar servidor (mostra IP local)
# -----------------------------
if __name__ == '__main__':
    # mostra IP local para acessar via outro dispositivo
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "127.0.0.1"
    print(f"\n✅ Servidor rodando em: http://{local_ip}:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
