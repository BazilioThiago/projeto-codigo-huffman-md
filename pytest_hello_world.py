import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import re
import os


# CONFIGURACAO DOS ARQUIVOS E PARAMETROS DO RELATORIO
ARQUIVOS_ETAPAS = {
    "1. Tarefa": "etapa1.csv",
    "2. Comportamental": "etapa2.csv",
    "3. Intertarefas": "etapa3.csv",
    "4. Sistema": "etapa4.csv",
}
ARQUIVO_10K = "etapa_10k.csv"  # Usado no Experimento B (convergencia)
PASTA_SAIDA = "resultados_graficos"

# Preencha com o resultado obtido no gcov (Experimento A) para sair na tabela
COBERTURA_ETAPA1 = "100% / 100%"

# Fator multiplicador sobre o HWM(100%) da Etapa 1 para definir o Deadline D fixo
FATOR_DEADLINE = 1.20

# Meta de (m, k) exigida para o calculo do menor D no Experimento D
META_MK_EXP_D = (18, 20)  # Ex.: cumprir pelo menos 18 de cada 20 ativacoes

os.makedirs(PASTA_SAIDA, exist_ok=True)
plt.rcParams.update({"figure.dpi": 150, "font.size": 10})


# FUNCOES AUXILIARES DE LEITURA E CALCULO
def carregar_csv_esp32(caminho: str) -> pd.DataFrame:
    """Lê o CSV gerado pelo ESP32 filtrando eventuais linhas de log da serial."""
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    linhas_validas = []
    padrao = re.compile(r"^\s*\d+\s*,\s*\d+(\.\d+)?\s*$")

    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
        for linha in f:
            if padrao.match(linha):
                partes = linha.strip().split(",")
                linhas_validas.append((int(partes[0]), float(partes[1])))

    if not linhas_validas:
        raise ValueError(f"Nenhuma medicao valida encontrada em {caminho}.")

    return pd.DataFrame(linhas_validas, columns=["ativacao", "tempo_us"])


def calcular_hwm_parcial(tempos: np.ndarray, percentil: float = 99.0) -> float:
    """Calcula o HWM(99%) desconsiderando o 1% de maiores medicoes."""
    ordenado = np.sort(tempos)
    idx = int(np.ceil((percentil / 100.0) * len(ordenado))) - 1
    idx = max(0, min(idx, len(ordenado) - 1))
    return float(ordenado[idx])


def analisar_perdas_e_rajadas(tempos: np.ndarray, deadline: float) -> dict:
    """Calcula perdas, distancias consecutivas, skip factor S e rajadas (Secao 6.3)."""
    violacoes = tempos > deadline
    indices_perda = np.where(violacoes)[0] + 1  # Base 1 (numero da ativacao)
    total_perdas = len(indices_perda)
    pct_no_prazo = 100.0 * (1.0 - total_perdas / len(tempos))

    if total_perdas == 0:
        return {
            "total_perdas": 0,
            "pct_no_prazo": 100.0,
            "indices_perda": indices_perda,
            "distancias": np.array([], dtype=int),
            "skip_factor": "N/A (0 perdas)",
            "num_rajadas": 0,
            "maior_rajada": 0,
            "perdas_isoladas": 0,
            "perdas_em_rajada": 0,
        }

    distancias = np.diff(indices_perda) if total_perdas >= 2 else np.array([], dtype=int)
    skip_factor = int(np.min(distancias)) if len(distancias) > 0 else "N/A (1 perda)"

    # Agrupa sequencias consecutivas de perdas (distancia == 1) para identificar rajadas
    grupos = []
    grupo_atual = [indices_perda[0]]
    for idx in indices_perda[1:]:
        if idx == grupo_atual[-1] + 1:
            grupo_atual.append(idx)
        else:
            grupos.append(grupo_atual)
            grupo_atual = [idx]
    grupos.append(grupo_atual)

    rajadas = [g for g in grupos if len(g) >= 2]
    perdas_isoladas = sum(1 for g in grupos if len(g) == 1)
    perdas_em_rajada = sum(len(g) for g in rajadas)
    maior_rajada = max((len(g) for g in rajadas), default=0)

    return {
        "total_perdas": total_perdas,
        "pct_no_prazo": pct_no_prazo,
        "indices_perda": indices_perda,
        "distancias": distancias,
        "skip_factor": skip_factor,
        "num_rajadas": len(rajadas),
        "maior_rajada": maior_rajada,
        "perdas_isoladas": perdas_isoladas,
        "perdas_em_rajada": perdas_em_rajada,
    }


def analisar_janela_deslizante(tempos: np.ndarray, deadline: float, k: int) -> dict:
    """Executa janela deslizante de tamanho k e extrai o (m, k)-firme (Secao 6.4)."""
    violacoes = (tempos > deadline).astype(int)
    if len(violacoes) < k:
        raise ValueError(f"Numero de amostras ({len(violacoes)}) menor que k={k}.")

    perdas_por_janela = np.convolve(violacoes, np.ones(k, dtype=int), mode="valid")
    perdas_max = int(np.max(perdas_por_janela))
    m = k - perdas_max

    return {
        "k": k,
        "m": m,
        "mk_str": f"({m},{k})",
        "perdas_max": perdas_max,
        "serie_perdas": perdas_por_janela,
    }


def encontrar_menor_d_para_mk(tempos: np.ndarray, m_alvo: int, k_alvo: int) -> float:
    """Encontra o menor deadline D na Etapa 4 que satisfaz (m_alvo, k_alvo)-firme."""
    max_perdas_toleradas = k_alvo - m_alvo
    candidatos = np.unique(np.sort(tempos))
    esq, dir_ = 0, len(candidatos) - 1
    melhor_d = float(candidatos[-1])

    while esq <= dir_:
        meio = (esq + dir_) // 2
        d_teste = float(candidatos[meio])
        res = analisar_janela_deslizante(tempos, d_teste, k_alvo)
        if res["perdas_max"] <= max_perdas_toleradas:
            melhor_d = d_teste
            dir_ = meio - 1
        else:
            esq = meio + 1

    return melhor_d


# GERACAO DE GRAFICOS (SECOES 6.2, 6.4 E EXPERIMENTO B)
def plotar_histograma_e_temporal(nome_etapa: str, df: pd.DataFrame, stats: dict, deadline: float):
    slug = nome_etapa.split(".")[0].strip()
    tempos = df["tempo_us"].values
    ativ = df["ativacao"].values

    # 1. Histograma (Secao 6.2)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.hist(tempos, bins=40, color="#4C72B0", edgecolor="white", alpha=0.85)
    ax.axvline(stats["hwm100"], color="#C44E52", linestyle="-", linewidth=1.8,
               label=f"HWM(100%) = {stats['hwm100']:.1f} µs")
    ax.axvline(stats["hwm99"], color="#DD8452", linestyle="--", linewidth=1.6,
               label=f"HWM(99%) = {stats['hwm99']:.1f} µs")
    ax.axvline(deadline, color="#2CA02C", linestyle="-.", linewidth=1.8,
               label=f"Deadline D = {deadline:.1f} µs")
    ax.set_title(f"Histograma dos Tempos de Resposta — {nome_etapa}")
    ax.set_xlabel("Tempo de Resposta (µs)")
    ax.set_ylabel("Frequência (ativações)")
    ax.legend()
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_SAIDA, f"etapa{slug}_histograma.png"))
    plt.close(fig)

    # 2. Grafico Temporal (Secao 6.2)
    fig, ax = plt.subplots(figsize=(9, 4.0))
    ax.plot(ativ, tempos, color="#4C72B0", linewidth=0.8, label="Tempo de resposta")
    ax.axhline(deadline, color="#2CA02C", linestyle="--", linewidth=1.5,
               label=f"Deadline D = {deadline:.1f} µs")

    # Destaca spikes (picos acima do HWM 99% ou acima de D)
    mask_picos = tempos > max(deadline, stats["hwm99"])
    if np.any(mask_picos):
        ax.scatter(ativ[mask_picos], tempos[mask_picos], color="#C44E52", s=18, zorder=4,
                   label="Picos / Violações")

    ax.set_title(f"Série Temporal do Tempo de Resposta — {nome_etapa}")
    ax.set_xlabel("Número da Ativação")
    ax.set_ylabel("Tempo de Resposta (µs)")
    ax.legend()
    ax.grid(True, linestyle=":", alpha=0.6)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_SAIDA, f"etapa{slug}_temporal.png"))
    plt.close(fig)


def plotar_janelas_deslizantes(nome_etapa: str, janelas: dict):
    slug = nome_etapa.split(".")[0].strip()
    fig, axes = plt.subplots(3, 1, figsize=(9, 7.5), sharex=False)

    for ax, k in zip(axes, [10, 20, 50]):
        info = janelas[k]
        serie = info["serie_perdas"]
        ax.plot(np.arange(1, len(serie) + 1), serie, color="#8172B3", linewidth=0.9)
        ax.axhline(info["perdas_max"], color="#C44E52", linestyle="--", linewidth=1.2,
                   label=f"Máx. perdas = {info['perdas_max']} → {info['mk_str']}-firme")
        ax.set_ylabel(f"Perdas (k={k})")
        ax.set_ylim(-0.3, max(info["perdas_max"] + 1.5, 2))
        ax.legend(loc="upper right")
        ax.grid(True, linestyle=":", alpha=0.6)

    axes[0].set_title(f"Perdas de Deadline por Janela Deslizante — {nome_etapa}")
    axes[-1].set_xlabel("Posição da Janela Deslizante")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_SAIDA, f"etapa{slug}_janela_mk.png"))
    plt.close(fig)


def plotar_convergencia_hwm(df_10k: pd.DataFrame):
    tempos = df_10k["tempo_us"].values
    n = np.arange(1, len(tempos) + 1)
    hwm_acumulado = np.maximum.accumulate(tempos)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(n, hwm_acumulado, color="#C44E52", linewidth=1.8, label="HWM acumulado (µs)")

    marcos = [10, 20, 100, 1000, 5000, len(tempos)]
    marcos = [m for m in marcos if m <= len(tempos)]
    ax.scatter(marcos, hwm_acumulado[np.array(marcos) - 1], color="#1F77B4", zorder=5)
    for m in marcos:
        val = hwm_acumulado[m - 1]
        ax.annotate(f"n={m}\n({val:.0f} µs)", (m, val), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8)

    ax.set_xscale("log")
    ax.set_title("Experimento B: Curva de Convergência do HWM Acumulado (escala log)")
    ax.set_xlabel("Número de Amostras (N)")
    ax.set_ylabel("HWM Acumulado (µs)")
    ax.grid(True, which="both", linestyle=":", alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_SAIDA, "experimentoB_convergencia_hwm.png"))
    plt.close(fig)

    return marcos, hwm_acumulado


def main():
    dados = {nome: carregar_csv_esp32(arq) for nome, arq in ARQUIVOS_ETAPAS.items()}

    # Define D fixo a partir da Etapa 1 (Secao 4)
    hwm1_100 = float(np.max(dados["1. Tarefa"]["tempo_us"].values))
    deadline_fixo = hwm1_100 * FATOR_DEADLINE

    print("=" * 80)
    print(f"DEADLINE FIXO ADOTADO (D = {FATOR_DEADLINE:.2f} x HWM_Etapa1): {deadline_fixo:.3f} us")
    print("=" * 80)

    linhas_tabela_sintese = []
    resultados_etapas = {}

    for nome, df in dados.items():
        tempos = df["tempo_us"].values
        t_min = float(np.min(tempos))
        t_med = float(np.mean(tempos))
        hwm100 = float(np.max(tempos))
        hwm99 = calcular_hwm_parcial(tempos, 99.0)

        perdas_info = analisar_perdas_e_rajadas(tempos, deadline_fixo)
        janelas = {k: analisar_janela_deslizante(tempos, deadline_fixo, k) for k in [10, 20, 50]}

        stats = {
            "min": t_min,
            "media": t_med,
            "hwm100": hwm100,
            "hwm99": hwm99,
            "perdas": perdas_info,
            "janelas": janelas,
        }
        resultados_etapas[nome] = stats

        # Gera graficos obrigatorios (6.2 e 6.4)
        plotar_histograma_e_temporal(nome, df, stats, deadline_fixo)
        plotar_janelas_deslizantes(nome, janelas)

        cobertura_col = COBERTURA_ETAPA1 if nome.startswith("1.") else "Mesma (100%)"
        linhas_tabela_sintese.append({
            "Etapa": nome,
            "Cobertura (linha/desvio)": cobertura_col,
            "Mín (µs)": f"{t_min:.2f}",
            "Média (µs)": f"{t_med:.2f}",
            "HWM(100%) (µs)": f"{hwm100:.2f}",
            "HWM(99%) (µs)": f"{hwm99:.2f}",
            "% no prazo": f"{perdas_info['pct_no_prazo']:.2f}%",
            "S": perdas_info["skip_factor"],
            "(m,k), k=10": janelas[10]["mk_str"],
            "(m,k), k=20": janelas[20]["mk_str"],
            "(m,k), k=50": janelas[50]["mk_str"],
        })

    # SECAO 8: TABELA-SINTESE OBRIGATORIA
    df_sintese = pd.DataFrame(linhas_tabela_sintese)
    print("\n--- SECAO 8: TABELA-SINTESE OBRIGATORIA ---")
    print(df_sintese.to_string(index=False))
    df_sintese.to_csv("tabela_sintese.csv", index=False)

    # SECAO 6.3: DETALHES DE PERDAS E RAJADAS POR ETAPA
    print("\n--- SECAO 6.3: DISTANCIAS ENTRE PERDAS, SKIP FACTOR E RAJADAS ---")
    for nome, st in resultados_etapas.items():
        p = st["perdas"]
        amostra_dist = p["distancias"][:15].tolist()
        print(f"\n[{nome}] Total de perdas: {p['total_perdas']} | Skip Factor S: {p['skip_factor']}")
        print(f"  Rajadas (consecutivas >= 2): {p['num_rajadas']} | Maior rajada: {p['maior_rajada']} perdas")
        print(f"  Perdas isoladas: {p['perdas_isoladas']} | Perdas em rajada: {p['perdas_em_rajada']}")
        if amostra_dist:
            print(f"  Primeiras distâncias entre perdas: {amostra_dist}")

    # EXPERIMENTO A: LIMITES DA COBERTURA
    print("\n--- EXPERIMENTO A: COBERTURA 100% vs CRESCIMENTO DO HWM ---")
    for nome, st in resultados_etapas.items():
        aumento = ((st["hwm100"] / hwm1_100) - 1.0) * 100.0
        print(f"  {nome:<20}: HWM(100%) = {st['hwm100']:8.2f} us ({aumento:+6.1f}% vs Etapa 1)")

    # EXPERIMENTO B: CONVERGENCIA DO HWM (10.000 AMOSTRAS)
    print("\n--- EXPERIMENTO B: CONVERGENCIA DO HWM ---")
    if os.path.exists(ARQUIVO_10K):
        df_10k = carregar_csv_esp32(ARQUIVO_10K)
    else:
        # Fallback: usa o maior dataset disponivel caso etapa_10k.csv nao exista
        maior_nome = max(dados, key=lambda k: len(dados[k]))
        df_10k = dados[maior_nome]
        print(f"  (Aviso: '{ARQUIVO_10K}' nao encontrado; usando '{maior_nome}' com {len(df_10k)} amostras)")

    marcos, hwm_acum = plotar_convergencia_hwm(df_10k)
    for m in marcos:
        print(f"  N = {m:<6} amostras -> HWM acumulado = {hwm_acum[m - 1]:.2f} us")

    # EXPERIMENTO C: MARGEM DE SEGURANCA FIXA SOBRE HWM DA ETAPA 1
    print("\n--- EXPERIMENTO C: MARGENS DE SEGURANCA FIXAS (10%, 25%, 50%) ---")
    for pct in [10, 25, 50]:
        limiar = hwm1_100 * (1.0 + pct / 100.0)
        etapas_estouradas = [
            nome for nome, st in resultados_etapas.items() if st["hwm100"] > limiar
        ]
        status = (
            f"Insuficiente a partir de: {etapas_estouradas[0]}"
            if etapas_estouradas
            else "Suficiente em todas as etapas"
        )
        print(f"  Margem +{pct}% ({limiar:.2f} us) -> {status}")

    # EXPERIMENTO D: VARIACAO DE DEADLINE NAS ETAPAS 3 E 4
    print("\n--- EXPERIMENTO D: VARIACAO DE D NAS ETAPAS 3 E 4 ---")
    hwm4_99 = resultados_etapas["4. Sistema"]["hwm99"]
    hwm4_100 = resultados_etapas["4. Sistema"]["hwm100"]
    d_intermediario = (hwm1_100 + hwm4_99) / 2.0

    deadlines_teste = {
        "D1 = HWM100(Etapa 1)": hwm1_100,
        "D2 = Intermediario": d_intermediario,
        "D3 = HWM99(Etapa 4)": hwm4_99,
    }

    for nome_etapa in ["3. Intertarefas", "4. Sistema"]:
        tempos = dados[nome_etapa]["tempo_us"].values
        print(f"\n  [{nome_etapa}]")
        for label_d, val_d in deadlines_teste.items():
            p = analisar_perdas_e_rajadas(tempos, val_d)
            mk20 = analisar_janela_deslizante(tempos, val_d, 20)["mk_str"]
            print(
                f"    {label_d:<22} ({val_d:7.2f} us) | No prazo: {p['pct_no_prazo']:6.2f}% | "
                f"S: {str(p['skip_factor']):<14} | (m,20): {mk20} | "
                f"Isoladas: {p['perdas_isoladas']} | Em rajada: {p['perdas_em_rajada']}"
            )

    m_alvo, k_alvo = META_MK_EXP_D
    tempos_etapa4 = dados["4. Sistema"]["tempo_us"].values
    d_min_mk = encontrar_menor_d_para_mk(tempos_etapa4, m_alvo, k_alvo)
    reducao_pct = (1.0 - d_min_mk / hwm4_100) * 100.0
    print(
        f"\n  Menor D na Etapa 4 que satisfaz ({m_alvo},{k_alvo})-firme: {d_min_mk:.2f} us "
        f"(vs HWM100 Etapa 4 = {hwm4_100:.2f} us -> reducao de {reducao_pct:.1f}% no prazo exigido)"
    )
    print(f"\nGraficos salvos na pasta '{PASTA_SAIDA}/' e tabela salva em 'tabela_sintese.csv'.")


if __name__ == "__main__":
    main()
