"""Gera relatorio de oito paginas a partir de medicoes existentes, sem inventar dados."""
import html, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).parent/'python_deps'))
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4


def report(folder):
    folder=pathlib.Path(folder); a=folder/'analise'; r=json.loads((a/'resumo.json').read_text()); ss=r['stages']
    identity=json.loads((pathlib.Path(__file__).resolve().parents[1]/'identificacao.json').read_text(encoding='utf-8-sig'))
    authors=' e '.join(person['nome'] for person in identity['integrantes'])
    people='<br/>'.join(html.escape(person['nome'])+' - RA: '+html.escape(person['ra'] or 'PREENCHER') for person in identity['integrantes'])
    out=pathlib.Path('output/pdf'); out.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name='Text',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=8))
    styles['Title'].fontSize=23; styles['Title'].leading=28
    styles['Heading1'].fontSize=17; styles['Heading1'].leading=21
    story=[]
    def p(t): story.append(Paragraph(t,styles['Text']))
    def h(t): story.append(Paragraph(t,styles['Heading1'])); story.append(Spacer(1,9))
    def page(): story.append(PageBreak())
    def img(name,width=490):
        from PIL import Image as PILImage
        im=PILImage.open(a/name); w,hh=im.size; story.append(Image(str(a/name),width=width,height=width*hh/w)); story.append(Spacer(1,8))
    def table(rows,widths=None,small=8):
        cells=[[Paragraph(str(c),ParagraphStyle(name='cell',fontSize=small,leading=small+3,textColor=colors.white if i==0 else colors.HexColor('#203345'))) for c in row] for i,row in enumerate(rows)]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT'); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#174c65')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#edf4f7'),colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7)])); story.append(t); story.append(Spacer(1,10))
    def fmt(x): return f'{x:.1f}'
    def skip(t): return str(t['skip']) if t['skip'] is not None else 'indef.'
    h('Tempo de resposta da tarefa Huffman')
    p(f'<b>Sistemas em Tempo Real - M3 | UNIVALI</b><br/>{html.escape(identity["curso"])}<br/>{people}')
    p(f'Campanha: {folder.name}. Dados obtidos em ESP32 física conectada à COM3. Este relatório é uma base técnica para revisão dos integrantes; as interpretações devem ser conferidas e compreendidas pelo grupo.')
    h('1. Plataforma e instrumentação')
    p('ESP32-D0WD-V3, revisão 3.1; dois núcleos Xtensa, CPU fixada em 160 MHz, cristal de 40 MHz. FreeRTOS SMP do ESP-IDF v6.1-dirty, tick de 1 ms, compilação Debug (-Og). Gerenciamento dinâmico de energia desativado; não há governor Linux. Wi-Fi e Bluetooth não são iniciados. O Windows executa o capturador serial, VS Code e aplicações listadas em processos_host.txt; não executa a tarefa medida.')
    p('Entrada de 1.024 bytes, rand()%256, srand(42) reiniciado em cada etapa. Cada ativação constrói a árvore, codifica, decodifica, compara com a entrada e libera as alocações. A geração da entrada fica fora da medição. CLOCK_MONOTONIC é lido via clock_gettime; resultados registrados em microssegundos inteiros.')
    p('Na etapa 1, mede-se entrada até retorno da tarefa. Nas etapas 2 a 4, mede-se do instante nominal do alarme até o retorno, incluindo entrega da interrupção, escalonamento, bloqueio e preempção. O instante nominal deriva da leitura monotônica anterior ao start do GPTimer de 1 MHz; o custo de iniciar o timer introduz pequeno viés conservador, não calibrado externamente.')
    p('Os tempos ficam na RAM (40 kB reservados) e são impressos apenas ao final de cada etapa, depois de interromper a carga. Assim, printf e transmissão serial não entram no intervalo medido nem intercalam as ativações. Interrupções normais do RTOS permanecem ativas. O coletor verifica índices, contagem, erros e marcador final.')
    p('Repositório: <link href="https://github.com/BazilioThiago/projeto-codigo-huffman-md" color="blue">github.com/BazilioThiago/projeto-codigo-huffman-md</link>. Fonte, configuração, testes, CSVs e scripts acompanham a entrega. As alterações locais ainda precisam ser publicadas pelos integrantes.')
    page(); h('2. Casos, procedimento e critérios')
    table([['Etapa / entradas e restrições','Procedimento e comportamento esperado'],
        ['1 - Tarefa / 1.000 ativações','Huffman no core 1, prioridade 3. Uma pausa de 1 tick entre execuções; nenhuma tarefa concorrente criada pela aplicação. Validação deve passar em todas.'],
        ['2 - Comportamental / 1.000','Evento de timer de disparo único após 30 ms; próximo evento só é armado depois de terminar o anterior. Acordar, executar e validar; um evento por vez.'],
        ['3 - Intertarefas / 1.000','Huffman periódico a 30 ms. No core 1, tarefas de prioridades 5 e 2 a cada 4 e 25 ms, com 500 e 1.200 us de trabalho e disputa por mutex. Medir espera e preempção.'],
        ['4 - Sistema / 10.000','Etapa 3 + interrupção de 120 us a cada 500 us no core 1 e carga de acessos a 32 KiB de RAM no core 0. Explorar disputa de CPU, memória e interrupções.']], [145,345])
    p('Critérios comuns: nenhuma falha de comparação, nenhuma perda de evento por overflow da fila e quantidade exata de amostras. A fila comporta 32 liberações; overflow aborta a campanha. O teste temporal busca perdas, portanto perder o deadline é um resultado experimental, não erro de validação. A carga do core 0 é sintética; não se presume saturação de cache ou equivalência com uma rede real.')
    p('Procedimento: fechar outros monitores; executar capture_monitor.ps1 -BuildFlash; aguardar CAMPANHA_CONCLUIDA; analisar a pasta datada. As etapas usam o mesmo firmware e algoritmo, mudando apenas o ambiente de execução. D é escolhido uma vez após a etapa 1 e aplicado às quatro etapas.')
    h('3. Experimento A - cobertura e corretude')
    p('GCC/gcov no host, com o mesmo huffman.c e alocadores substituídos apenas para injetar falhas: entrada vazia, ponteiro nulo, tamanho inválido, símbolo único, todos os símbolos, centenas de tamanhos aleatórios e falha em cada ponto de alocação. Resultado: <b>113/113 linhas (100%) e 71/74 resultados de desvios (95,95%)</b>. Os três resultados restantes exigem nó com filho direito e sem filho esquerdo, impossível na árvore binária cheia construída. Não se fabricaram árvores inválidas para elevar a cobertura.')
    p(f"Essa suíte funcional é separada da medição em placa: cobertura do host não é cobertura medida do firmware. Não houve instante com 100% de desvios; portanto não se afirma ter registrado HWM nesse instante. O HWM da etapa 1 validada foi {fmt(ss['1']['hwm'])} us; etapas 2, 3 e 4: {', '.join(fmt(ss[s]['hwm']) for s in ('2','3','4'))} us. Cobertura de linha/desvio não representa todos os caminhos nem fases de hardware e escalonamento.")
    page(); h('4. Síntese e histogramas')
    p(f"<b>D fixo = 1,2 × {fmt(ss['1']['hwm'])} = {fmt(r['D'])} us.</b> Cumprimento: tempo ≤ D. HWM99 remove exatamente 1% das maiores observações (10 nas etapas 1-3 e 100 na etapa 4).")
    table([['Etapa','Cob.<br/>L/D*','Mín.','Média','HWM<br/>100%','HWM<br/>99%','% no<br/>prazo','S','(m,10)','(m,20)','(m,50)'], *[[s,'100/95,95',fmt(t['minimum']),fmt(t['mean']),fmt(t['hwm']),fmt(t['hwm99']),f"{t['on_time_pct']:.2f}",skip(t),*[str(tuple(t['mk'][str(k)])) for k in (10,20,50)]] for s,t in ss.items()]], [35,44,46,46,46,46,40,29,53,53,53],7)
    p('*Cobertura da suíte funcional no host, comum ao fonte das quatro etapas; não medida por cenário. Tempos em us. A tabela-síntese inclui S e (m,k); as janelas são detalhadas na página 5.')
    img('histogramas.png')
    for s,t in ss.items(): p(f"Etapa {s}: os 90% centrais ficam entre {fmt(t['q05'])} e {fmt(t['q95'])} us; mediana {fmt(t['median'])} us. A cauda acima de HWM99 alcança mais {fmt(t['hwm']-t['hwm99'])} us ({100*(t['hwm']-t['hwm99'])/t['median']:.2f}% da mediana), descrevendo sua extensão relativa.")
    page(); h('5. Sequências temporais e perdas')
    img('temporais.png')
    p('Pontos vermelhos excedem o D fixo; pontos roxos destacam os extremos acima de HWM99. A linha tracejada marca D. A ordem das ativações é preservada. Histogramas mostram frequência, mas a sequência temporal revela agrupamentos. Na etapa 4 há picos recorrentes, compatíveis com a carga periódica; isso é uma interpretação do padrão, não uma identificação causal isolada. Com D fixo, todas as ativações dessa etapa pertencem à mesma rajada de perdas.')
    table([['Etapa','Perdas','Isoladas','Rajadas (≥2)','Maior rajada','S'],*[[s,len(t['losses']),t['isolated'],len(t['bursts']),t['longest_burst'],skip(t)] for s,t in ss.items()]], [50,80,90,100,100,70])
    p('S é a menor diferença entre os índices de duas perdas consecutivas; S=1 indica perdas adjacentes. Com zero ou uma perda, S é indefinido. Uma rajada é uma sequência maximal de duas ou mais perdas; uma perda sem vizinhas é isolada. As listas completas estão nos arquivos perdas_etapaN.csv e distancias_etapaN.csv, evitando omitir ativações do relatório de dados.')
    for s,t in ss.items():
        p(f"Etapa {s}: {len(t['losses'])} perdas; {t['isolated']} isoladas e {len(t['bursts'])} rajadas. Primeiros índices: {str(t['losses'][:12])}. Primeiras distâncias: {str(t['distances'][:12])}.")
    page(); h('6. Janelas deslizantes e (m,k)-firme')
    table([['Etapa','S','(m,10)','(m,20)','(m,50)'],*[[s,skip(t),*[str(tuple(t['mk'][str(k)])) for k in (10,20,50)]] for s,t in ss.items()]], [50,80,120,120,120])
    img('janelas.png',440)
    p('Para cada k, contam-se as perdas nas N-k+1 janelas completas. m=k-máximo de perdas. A tabela descreve o pior caso observado, não uma garantia formal para futuras ativações. As séries completas de cada janela acompanham os dados.')
    page(); h('7. Experimentos B e C')
    img('convergencia.png')
    table([['Amostras (etapa 4)','10','20','100','1.000','10.000'],['HWM acumulado (us)',*[fmt(r['convergence'][str(n)]) for n in (10,20,100,1000,10000)]]],[130,72,72,72,72,72])
    p(f"O máximo final da etapa 4 apareceu na ativação {r['last_hwm_activation']}. O HWM com 20 amostras foi {fmt(r['convergence']['20'])} us, contra {fmt(ss['4']['hwm'])} us ao fim. Um patamar posterior ao último salto significa apenas ausência de novos máximos nesta sequência; não prova convergência ao WCRT. A curva acumulada nunca diminui por definição.")
    table([['Margem sobre HWM1','Limite (us)','Etapas que excedem'],*[[f'{100*float(m):.0f}%',fmt(t['threshold']),str(t['exceeded_in'])] for m,t in r['margins'].items()]], [150,120,220])
    p(f"HWM da etapa 4: {fmt(ss['4']['hwm'])} us. A suficiência das margens é avaliada contra cada máximo observado, sem mudar D na comparação principal. Uma margem fixa pode falhar quando interrupções e bloqueios alteram a distribuição. No exemplo 12-14 ms versus 10-16 ms, a segunda faixa é mais variável apesar de um centro semelhante: média e cobertura não justificam sozinhas uma margem.")
    page(); h('8. Experimento D - variar apenas o deadline')
    p('Reanálise dos mesmos tempos das etapas 3 e 4 para três deadlines: HWM100 da etapa 1, HWM99 da etapa 4 e ponto médio. Não é uma nova coleta nem altera o D fixo das páginas anteriores. Listas de perdas, distâncias, janelas k=10,20,50 e gráficos adicionais estão nos arquivos D1/D2/D3 e deadlines_etapaN.png.')
    table([['Etapa','D (us)','% prazo','S','(m,20)','Isoladas / rajadas'],*[[s,fmt(t['deadline']),f"{t['on_time_pct']:.2f}",skip(t),str(tuple(t['mk']['20'])),f"{t['isolated']} / {len(t['bursts'])}"] for s,items in r['experiment_D'].items() for t in items]], [42,85,80,45,100,138])
    h('Critério escolhido: (18,20)')
    p('Exige pelo menos 18 cumprimentos em toda janela de 20 ativações, isto é, permite no máximo duas perdas por janela. É uma escolha experimental do grupo para demonstrar o método; não foi derivada de um requisito de segurança de uma planta física.')
    p(f"<b>Menor D observado que satisfaz (18,20): {fmt(r['minimum_D_18_20'])} us.</b> Cálculo exato: encontrar o 18º menor tempo de cada janela de 20 e tomar o maior desses valores. Um D menor falha na janela que determina o máximo. Em comparação, D=HWM100 da etapa 4 é {fmt(ss['4']['hwm'])} us e cumpre todos os deadlines observados; a redução é {100*(1-r['minimum_D_18_20']/ss['4']['hwm']):.2f}%.")
    p('Em um sistema com inércia física, o efeito de uma atualização perdida pode ser amortecido se houver recuperações entre perdas. Perdas adjacentes prolongam a ausência de informação ou atuação. Dois traços com o mesmo percentual podem ter consequências diferentes; S, rajadas e janelas capturam parte dessa diferença. O critério precisa ser ligado à dinâmica real antes de servir como requisito de operação.')
    p('O modelo (m,k) não limita, sozinho, o atraso absoluto de uma ativação perdida, nem prova estabilidade do controle. É um critério mensurável aplicado ao traço; garantias exigem análise e hipóteses adicionais.')
    page(); h('9. Interpretação, validade e conclusão')
    p('A suíte lógica exercita o algoritmo e seus tratamentos de erro. Ela não enumera o momento de chegada de interrupções, a fase das tarefas, estados do alocador, barramento ou cache. Portanto, mesmo com cobertura de linhas saturada, o máximo pode mudar com o escopo e com o número de amostras. O HWM é um limite inferior observado para o verdadeiro pior caso, não um limite superior seguro.')
    p(f"Nesta campanha, os HWM das quatro etapas foram {', '.join(fmt(ss[s]['hwm']) for s in ('1','2','3','4'))} us. Os dados devem ser interpretados como medidos; não existe obrigação de o máximo crescer estritamente de uma etapa para outra. A etapa 4 também tem dez vezes mais amostras, fator adicional de exposição a extremos.")
    h('Ameaças à validade')
    p('<b>Instrumentação:</b> clock_gettime, fila e armazenamento têm custo; a memória reservada muda o estado do sistema. O início nominal do timer usa duas chamadas distintas, com viés de fase. Não houve validação com analisador lógico ou calibração independente da deriva entre relógios.')
    p('<b>Escopo:</b> carga sintética finita, sem tráfego Wi-Fi/BT, DMA ou periféricos reais. O RTOS reduz algumas fontes de variabilidade do desktop, mas mantém interrupções e recursos compartilhados. A configuração a 160 MHz é fixa; outro build ou frequência muda os tempos.')
    p('<b>Amostragem:</b> uma campanha, mesma semente e ordem 1 a 4. Estados de heap/cache e alinhamento das tarefas podem favorecer ou desfavorecer a observação do pior caso. Repetições com outras fases e sementes são necessárias para ampliar a evidência, preservando a definição do cenário.')
    p('<b>Cobertura:</b> obtida em GCC/MinGW, não no executável Xtensa. Não se atingiu 100% dos resultados de desvios pelas condições estruturalmente impossíveis documentadas; 100% das linhas não é 100% dos caminhos. A comparação com tempos é entre a suíte lógica e a campanha sem gcov, evitando misturar o custo da instrumentação de cobertura.')
    h('Conclusão e reprodução')
    p('A medição de resposta deve incluir espera, bloqueio e preempção quando esses efeitos fazem parte do cenário. O registro em RAM evita imprimir entre amostras; a captura exclusiva da serial elimina a dependência do monitor interativo. Os CSVs preservam cada ativação e permitem reproduzir os gráficos e critérios.')
    p('O (m,k) transforma tolerância a perdas em uma verificação objetiva por janela, mas o valor medido descreve apenas este traço. O relatório não afirma ter encontrado o WCRT. Antes de entregar, os integrantes devem revisar as interpretações, preencher seus RAs, publicar os fontes e renomear o ZIP no padrão solicitado.')
    p('Arquivos: main/ (tarefa e instrumentação), tools/ (captura, testes, análise e relatório), resultados/cobertura/ (gcov), pasta datada (CSV e log), analise/ (tabelas, listas e gráficos). Fonte dos requisitos: Atividade.pdf, fornecido com o projeto.')
    def footer(c,doc):
        c.setFont('Helvetica',8); c.setFillColor(colors.HexColor('#526b7a')); c.drawString(42,24,'UNIVALI | Sistemas em Tempo Real | Huffman / ESP32'); c.drawRightString(A4[0]-42,24,str(doc.page))
    doc=SimpleDocTemplate(str(out/'relatorio_huffman.pdf'),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=36,bottomMargin=42,title='Medicoes de tempo de resposta - Huffman',author=authors)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(out/'relatorio_huffman.pdf')

if __name__=='__main__': report(sys.argv[1])


