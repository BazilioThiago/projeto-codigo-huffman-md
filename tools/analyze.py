"""Analise reprodutivel; tempos em us, perdas quando tempo > D."""
import argparse, csv, json, math, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).parent/'python_deps'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def deadline_stats(values, d):
    lost = np.asarray(values)>d
    positions = np.flatnonzero(lost)+1
    distances = np.diff(positions)
    runs=[]
    for p in positions.tolist():
        if runs and p == runs[-1][-1]+1: runs[-1].append(p)
        else: runs.append([p])
    windows={k:np.convolve(lost.astype(int), np.ones(k,dtype=int),'valid') for k in (10,20,50)}
    return dict(deadline=float(d),on_time_pct=float(100*(1-lost.mean())),losses=positions.tolist(),
        distances=distances.tolist(),skip=int(distances.min()) if len(distances) else None,
        isolated=sum(len(r)==1 for r in runs),bursts=[r for r in runs if len(r)>=2],
        longest_burst=max([len(r) for r in runs if len(r)>=2], default=0),
        mk={str(k):[k-int(w.max()),k] for k,w in windows.items()}), windows


def minimum_deadline(values, m=18,k=20):
    # Each window needs its m-th smallest value <= D. Maximum over all windows is exact.
    return float(max(np.partition(values[i:i+k],m-1)[m-1] for i in range(len(values)-k+1)))


def write_csv(path,header,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(header); w.writerows(rows)


def analyze(folder):
    folder=pathlib.Path(folder); out=folder/'analise'; out.mkdir(exist_ok=True)
    if not (folder/'complete.json').exists(): raise ValueError('Campanha sem marcador de conclusao; nao analisar dados parciais.')
    data={}
    for stage in range(1,5):
        with (folder/f'etapa{stage}.csv').open() as f: rows=list(csv.DictReader(f))
        assert len(rows)==(10000 if stage==4 else 1000)
        assert [int(r['ativacao']) for r in rows]==list(range(1,len(rows)+1))
        data[stage]=np.array([float(r['tempo_us']) for r in rows])
        assert np.all(np.isfinite(data[stage])) and np.all(data[stage]>0)
    d=float(data[1].max()*1.2)
    result={'D':d,'stages':{},'margins':{},'experiment_D':{},'required_mk':[18,20]}
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    fig_hist,axh=plt.subplots(2,2,figsize=(10,6),layout='constrained')
    fig_time,axt=plt.subplots(2,2,figsize=(10,6),layout='constrained')
    fig_win,axw=plt.subplots(4,1,figsize=(10,8),layout='constrained')
    for stage,v in data.items():
        stats,windows=deadline_stats(v,d)
        stats.update(n=len(v),minimum=float(v.min()),mean=float(v.mean()),median=float(np.median(v)),q05=float(np.quantile(v,.05)),q95=float(np.quantile(v,.95)),hwm=float(v.max()),
            hwm99=float(np.sort(v)[len(v)-math.floor(.01*len(v))-1]))
        result['stages'][stage]=stats
        write_csv(out/f'perdas_etapa{stage}.csv',['ativacao'],[[i] for i in stats['losses']])
        write_csv(out/f'distancias_etapa{stage}.csv',['perda_anterior','perda_seguinte','distancia'],zip(stats['losses'],stats['losses'][1:],stats['distances']))
        for k,w in windows.items(): write_csv(out/f'janelas_etapa{stage}_k{k}.csv',['inicio','perdas'],enumerate(w,1))
        ax=axh.flat[stage-1]; ax.hist(v,bins=50,color='#247b97'); ax.axvline(d,color='#cc4433',label='D fixo'); ax.axvline(v.max(),color='#8353a5',linestyle='--',label='HWM'); ax.set(title=f'Etapa {stage}',xlabel='Tempo (us)',ylabel='Frequencia (log)',yscale='log'); ax.legend(fontsize=7)
        ax=axt.flat[stage-1]; ax.plot(np.arange(1,len(v)+1),v,lw=.5,color='#247b97'); ix=np.flatnonzero(v>d); ax.scatter(ix+1,v[ix],s=3,c='#cc4433',label='Perda'); peaks=np.flatnonzero(v>stats['hwm99']); ax.scatter(peaks+1,v[peaks],s=7,c='#8353a5',label='Cauda > HWM99'); ax.axhline(d,color='#cc4433',ls='--',label='D'); ax.legend(fontsize=6); ax.set(title=f'Etapa {stage}',xlabel='Ativacao',ylabel='Tempo (us)')
        ax=axw[stage-1]
        for k,w in windows.items(): ax.plot(np.arange(1,len(w)+1),w,lw=.7,label=f'k={k}, m={stats["mk"][str(k)][0]}')
        ax.set(title=f'Etapa {stage}',xlabel='Inicio da janela',ylabel='Perdas',ylim=(-1,51),yticks=[0,10,20,30,40,50]); ax.legend(loc='upper right',fontsize=7,ncol=3)
    for f,name in ((fig_hist,'histogramas'),(fig_time,'temporais'),(fig_win,'janelas')):
        f.savefig(out/f'{name}.png',dpi=180); plt.close(f)
    fig,ax=plt.subplots(figsize=(9,3.5),layout='constrained')
    for stage,v in data.items(): ax.plot(np.arange(1,len(v)+1),np.maximum.accumulate(v),label=f'Etapa {stage}')
    ax.set(xscale='log',xlabel='Numero de amostras',ylabel='HWM acumulado (us)'); ax.legend(); fig.savefig(out/'convergencia.png',dpi=180); plt.close(fig)
    result['convergence']={n:float(data[4][:n].max()) for n in (10,20,100,1000,10000)}
    result['last_hwm_activation']=int(np.argmax(data[4])+1)
    for margin in (.10,.25,.50):
        threshold=float(data[1].max()*(1+margin))
        result['margins'][str(margin)]={'threshold':threshold,'exceeded_in':[s for s,v in data.items() if v.max()>threshold]}
    d1=float(data[1].max()); d4=result['stages'][4]['hwm99']
    deadlines=sorted(set([d1,(d1+d4)/2,d4]))
    if len(deadlines)<3: deadlines=[d1*.9,d1,d1*1.1]
    for stage in (3,4):
        result['experiment_D'][stage]=[]
        for j,dd in enumerate(deadlines,1):
            stats,win=deadline_stats(data[stage],dd); result['experiment_D'][stage].append(stats)
            write_csv(out/f'D{j}_etapa{stage}_perdas.csv',['ativacao'],[[i] for i in stats['losses']])
            write_csv(out/f'D{j}_etapa{stage}_distancias.csv',['distancia'],[[i] for i in stats['distances']])
            for k,w in win.items(): write_csv(out/f'D{j}_etapa{stage}_k{k}.csv',['inicio','perdas'],enumerate(w,1))
        fig,axs=plt.subplots(3,1,figsize=(9,6),layout='constrained')
        for ax,dd in zip(axs,deadlines):
            st,win=deadline_stats(data[stage],dd)
            for k,w in win.items(): ax.plot(np.arange(1,len(w)+1),w,lw=.6,label=f'k={k}')
            ax.set(title=f'Etapa {stage}, D={dd:.1f} us',xlabel='Inicio da janela',ylabel='Perdas',ylim=(-1,51),yticks=[0,10,20,30,40,50]); ax.legend(ncol=3,fontsize=7)
        fig.savefig(out/f'deadlines_etapa{stage}.png',dpi=180); plt.close(fig)
    result['minimum_D_18_20']=minimum_deadline(data[4])
    assert deadline_stats(data[4],result['minimum_D_18_20'])[0]['mk']['20'][0]>=18
    result['coverage']={'lines':100.,'branches':95.95,'platform':'host GCC/MinGW; suite funcional separada, sem gcov no firmware'}
    (out/'resumo.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    write_csv(out/'sintese.csv',['etapa','n','min_us','media_us','HWM100_us','HWM99_us','percentual_no_prazo','S','mk10','mk20','mk50'],
        [[s,t['n'],t['minimum'],t['mean'],t['hwm'],t['hwm99'],t['on_time_pct'],t['skip'],*[str(t['mk'][str(k)]) for k in (10,20,50)]] for s,t in result['stages'].items()])
    print(json.dumps({k:v for k,v in result.items() if k not in ('stages','experiment_D')},indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('folder'); analyze(p.parse_args().folder)
